import logging
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from client.models import Client, ClientFollow
from client.permissions import IsAccountOwnerOrStaff
from client.utils import verify_and_extract_client_id
from client.serializers import (
    ClientSerializer,
    ClientRegisterSerializer,
    ClientUpdateSerializer,
    PublicProfileSerializer,
    StudentPublicProfileSerializer,
    TeacherPublicProfileSerializer,
    ModeratorPublicProfileSerializer,
    ClientFollowSerializer,
)
from client.mail import EmailDeliveryError
from django.db.models import Count, Exists, OuterRef, Value, BooleanField


logger = logging.getLogger(__name__)


class PublicUserProfileView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    lookup_field = 'id'

    def get_serializer_class(self):
        """Return role-specific serializer based on the profile being viewed."""
        obj = self.get_object()
        if obj.is_teacher:
            return TeacherPublicProfileSerializer
        elif obj.is_student:
            return StudentPublicProfileSerializer
        elif obj.is_moderator:
            return ModeratorPublicProfileSerializer
        return PublicProfileSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        user = self.request.user

        if user.is_authenticated:
            is_followed_subquery = ClientFollow.objects.filter(
                follower=user,
                following=OuterRef('pk')
            )
            followed_annotation = Exists(is_followed_subquery)
        else:
            followed_annotation = Value(False, output_field=BooleanField())

        return Client.objects.filter(is_active=True).select_related(
            'student_account', 'teacher_account', 'moderator_account'
        ).prefetch_related(
            'follower_relationships', 'following_relationships'
        ).annotate(
            followers_count=Count('follower_relationships', distinct=True),
            following_count=Count('following_relationships', distinct=True),
            followed_by_current_user=followed_annotation
        )


class ToggleFollowView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClientFollowSerializer

    def create(self, request, *args, **kwargs):
        target_id = kwargs.get('id')

        if str(request.user.id) == str(target_id):
            return Response({"error": "You cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user = Client.objects.get(id=target_id, is_active=True)
        except Client.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        follow_obj, created = ClientFollow.objects.get_or_create(
            follower=request.user,
            following=target_user
        )

        if not created:
            follow_obj.delete()
            return Response({"status": "unfollowed", "is_followed": False}, status=status.HTTP_200_OK)

        serializer = self.get_serializer(follow_obj)
        return Response({"status": "followed", "is_followed": True, "follow": serializer.data}, status=status.HTTP_201_CREATED)


class FollowersListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicProfileSerializer
    pagination_class = None

    def get_queryset(self):
        user_id = self.kwargs['id']
        return Client.objects.filter(
            following_relationships__following_id=user_id,
            is_active=True
        ).annotate(
            followers_count=Count('follower_relationships', distinct=True),
            following_count=Count('following_relationships', distinct=True),
        ).order_by('-following_relationships__created_at')


class FollowingListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicProfileSerializer
    pagination_class = None

    def get_queryset(self):
        user_id = self.kwargs['id']
        return Client.objects.filter(
            follower_relationships__follower_id=user_id,
            is_active=True
        ).annotate(
            followers_count=Count('follower_relationships', distinct=True),
            following_count=Count('following_relationships', distinct=True),
        ).order_by('-follower_relationships__created_at')


class ClientRegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = ClientRegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            client_instance = serializer.save()
        except EmailDeliveryError:
            return Response(
                {"detail": "The email service is temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        
        # Generate tokens for immediate login after verification
        refresh = RefreshToken.for_user(client_instance)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        
        return Response(
            {
                "access": access_token,
                "refresh": refresh_token,
                "user": {
                    "id": str(client_instance.id),
                    "email": client_instance.email,
                    "display_name": client_instance.display_name,
                    "role": client_instance.role,
                }
            },
            status=status.HTTP_201_CREATED
        )


class EmailVerifyView(APIView):
    """Verify email with 6-digit OTP."""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email', '').lower().strip()
        otp = request.data.get('otp', '').strip()

        if not email or not otp:
            return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        if len(otp) != 6 or not otp.isdigit():
            return Response({"error": "Invalid OTP format. Must be 6 digits."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = Client.objects.get(email__iexact=email, is_active=True)
        except Client.DoesNotExist:
            return Response({"error": "Invalid OTP or user not found."}, status=status.HTTP_400_BAD_REQUEST)

        if client.is_verified:
            return Response({"error": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        if verify_otp(str(client.id), otp):
            client.is_verified = True
            client.save(update_fields=['is_verified'])
            logger.info(f"Email verified for user {client.id}")

            # Generate tokens for immediate login
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(client)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

            response = Response(
                {
                    "access": access_token,
                    "user": {
                        "id": str(client.id),
                        "email": client.email,
                        "display_name": client.display_name,
                        "role": client.role,
                    }
                },
                status=status.HTTP_200_OK
            )
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
                domain=getattr(settings, 'REFRESH_COOKIE_DOMAIN', None),
                path="/",
                max_age=7 * 24 * 60 * 60,
            )
            return response

        return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)


class ClientListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClientSerializer
    pagination_class = None

    def get_queryset(self):
        if not self.request.user.is_staff:
            return Client.objects.none()
        return Client.objects.all().order_by('-created_at')


class ClientDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Client.objects.all()
        return Client.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return ClientUpdateSerializer
        return ClientSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response({"detail": "Your account has been deactivated."}, status=status.HTTP_200_OK)


class ClientHardDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    lookup_field = 'pk'
    queryset = Client.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.check_object_permissions(request, instance)
        instance.delete()
        return Response({"detail": "Your account has been permanently deleted."}, status=status.HTTP_204_NO_CONTENT)
