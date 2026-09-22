import logging
import random
from django.conf import settings
from django.core.cache import cache
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from auth.serializers import PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from client.models import Client
from client.mail import EmailDeliveryError, send_templated_email
from client.utils import (
    generate_password_reset_token, verify_and_extract_reset_id,
    generate_otp, store_otp, verify_otp, resend_otp_allowed, set_resend_cooldown
)

logger = logging.getLogger(__name__)


class CurrentUserView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        return Response(
            {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "is_verified": user.is_verified,
            },
            status=status.HTTP_200_OK,
        )


class SecureLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(str(e))

        user = serializer.user
        if not user.is_verified:
            return Response(
                {"error": "Please verify your email address before logging in."},
                status=status.HTTP_403_FORBIDDEN
            )

        data = serializer.validated_data
        access_token = data["access"]
        refresh_token = data["refresh"]

        response = Response(
            {
                "access": access_token,
                "refresh": refresh_token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                    "is_verified": user.is_verified,
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


class SecureTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get('refresh_token')
        if not refresh_token:
            return Response(
                {"error": "Authentication credentials missing or session expired."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        mutable_data = request.data.copy()
        mutable_data['refresh'] = refresh_token

        serializer = self.get_serializer(data=mutable_data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(str(e))

        data = serializer.validated_data
        new_access_token = data["access"]
        new_refresh_token = data.get("refresh")

        response = Response({"access": new_access_token}, status=status.HTTP_200_OK)

        if new_refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=new_refresh_token,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
                domain=getattr(settings, 'REFRESH_COOKIE_DOMAIN', None),
                path="/",
                max_age=7 * 24 * 60 * 60,
            )
        return response


class SecureLogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get('refresh_token')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass

        response = Response({"detail": "Logout successful."}, status=status.HTTP_200_OK)
        response.delete_cookie(
            key="refresh_token",
            domain=getattr(settings, 'REFRESH_COOKIE_DOMAIN', None),
            path="/",
        )
        return response


class PasswordResetRequestView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        try:
            client = Client.objects.get(email__iexact=email, is_active=True)
            token = generate_password_reset_token(str(client.id))
            self.send_reset_email(client, token)
        except EmailDeliveryError:
            return Response(
                {"message": "The email service is temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Client.DoesNotExist:
            logger.info(f"Password reset requested for unregistered/inactive address: {email}")

        return Response(
            {"message": "If an active account exists with that email address, a password reset link has been dispatched."},
            status=status.HTTP_200_OK
        )

    def send_reset_email(self, client, token):
        domain = getattr(settings, 'EMAIL_FRONTEND_URL', 'http://localhost:3000').rstrip("/")
        reset_url = f"{domain}/auth/password-reset-confirm?token={token}"

        context = {"name": client.display_name, "reset_url": reset_url}
        send_templated_email(
            subject="Reset your password",
            recipient=client.email,
            template_name="emails/password_reset.html",
            context=context,
        )


class PasswordResetConfirmView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        password = serializer.validated_data['password']

        client_id = verify_and_extract_reset_id(token)
        if not client_id:
            return Response({"error": "The reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = Client.objects.get(pk=client_id, is_active=True)
        except Client.DoesNotExist:
            return Response({"error": "User associated with this token does not exist."}, status=status.HTTP_404_NOT_FOUND)

        client.set_password(password)
        client.save(update_fields=['password'])

        return Response({"message": "Your password has been successfully reset. You may now log in."}, status=status.HTTP_200_OK)




class ResendVerificationView(APIView):
    """Resend verification OTP."""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email', '').lower().strip()

        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = Client.objects.get(email__iexact=email, is_active=True)
        except Client.DoesNotExist:
            # Don't reveal if user exists
            return Response({"message": "If an account exists with that email, a new verification code has been sent."}, status=status.HTTP_200_OK)

        if client.is_verified:
            return Response({"error": "Email is already verified."}, status=status.HTTP_400_BAD_REQUEST)

        if not resend_otp_allowed(str(client.id)):
            return Response({"error": "Please wait before requesting a new code."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        otp = generate_otp()
        store_otp(str(client.id), otp)
        set_resend_cooldown(str(client.id))

        try:
            self.send_verification_email(client, otp)
        except EmailDeliveryError:
            return Response(
                {"error": "The email service is temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response({"message": "A new verification code has been sent."}, status=status.HTTP_200_OK)

    def send_verification_email(self, client, otp):
        domain = getattr(settings, 'EMAIL_FRONTEND_URL', 'http://localhost:3000').rstrip("/")
        context = {
            "name": client.display_name or client.first_name,
            "otp": otp,
            "domain": domain,
        }
        send_templated_email(
            subject="Your verification code",
            recipient=client.email,
            template_name="emails/verify_email_otp.html",
            context=context,
        )