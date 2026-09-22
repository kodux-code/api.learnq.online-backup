from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta


from .models import StudentAccount, TeacherAccount, ModeratorAccount
from .serializers import (
    StudentAccountSerializer,
    TeacherAccountSerializer,
    TeacherAccountPublicSerializer,
    TeacherAccountUpdateSerializer,
    ModeratorAccountSerializer,
    ModeratorAccountUpdateSerializer,
)
from client.permissions import IsAccountOwnerOrStaff
from client.models import Client
from course.models import Course, Enrollment, Review


class StudentAccountView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = StudentAccountSerializer

    def get_object(self):
        return get_object_or_404(StudentAccount, client=self.request.user)


class TeacherAccountView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return TeacherAccountUpdateSerializer
        return TeacherAccountSerializer

    def get_object(self):
        return get_object_or_404(TeacherAccount, client=self.request.user)


class TeacherPublicProfileView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = TeacherAccountPublicSerializer
    lookup_field = 'client__id'
    lookup_url_kwarg = 'teacher_id'

    def get_queryset(self):
        return TeacherAccount.objects.select_related('client').filter(
            client__is_active=True,
            client__role=Client.Role.TEACHER
        )


class TeacherListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TeacherAccountPublicSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = TeacherAccount.objects.select_related('client').filter(
            client__is_active=True,
            client__role=Client.Role.TEACHER
        )

        # Filter by course category if provided
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(
                client__teacher_courses__course__category__slug=category,
                client__teacher_courses__is_active=True
            ).distinct()

        # Filter by minimum rating
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            try:
                queryset = queryset.filter(rating__gte=float(min_rating))
            except ValueError:
                pass

        # Ordering
        ordering = self.request.query_params.get('ordering', '-rating')
        valid_orderings = ['rating', '-rating', 'total_students', '-total_stourses', 'review_count', '-review_count', 'created_at', '-created_at']
        if ordering in valid_orderings:
            queryset = queryset.order_by(ordering)

        return queryset


class ModeratorAccountView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return ModeratorAccountUpdateSerializer
        return ModeratorAccountSerializer

    def get_object(self):
        return get_object_or_404(ModeratorAccount, client=self.request.user)


class CurrentUserAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.is_student:
            account = get_object_or_404(StudentAccount, client=user)
            serializer = StudentAccountSerializer(account)
        elif user.is_teacher:
            account = get_object_or_404(TeacherAccount, client=user)
            serializer = TeacherAccountSerializer(account)
        elif user.is_moderator:
            account = get_object_or_404(ModeratorAccount, client=user)
            serializer = ModeratorAccountSerializer(account)
        else:
            return Response({"error": "No account profile found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(serializer.data)


class TeacherStatsView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    serializer_class = TeacherAccountSerializer

    def get_object(self):
        return get_object_or_404(TeacherAccount, client=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Add detailed stats
        teacher = instance.client
        courses = Course.objects.filter(course_teachers__teacher=teacher, course_teachers__is_active=True)

        data['detailed_stats'] = {
            'published_courses': courses.filter(status=Course.Status.PUBLISHED).count(),
            'draft_courses': courses.filter(status=Course.Status.DRAFT).count(),
            'total_lectures': sum(c.total_lectures for c in courses),
            'total_duration_hours': sum(c.total_duration_minutes for c in courses) / 60,
            'monthly_students': Enrollment.objects.filter(
                course__course_teachers__teacher=teacher,
                course__course_teachers__is_active=True,
                enrolled_at__gte=timezone.now() - timedelta(days=30)
            ).count(),
            'completion_rate': self._calculate_completion_rate(teacher),
        }

        return Response(data)

    def _calculate_completion_rate(self, teacher):
        from django.utils import timezone
        from datetime import timedelta
        enrollments = Enrollment.objects.filter(
            course__course_teachers__teacher=teacher,
            course__course_teachers__is_active=True,
            status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED]
        )
        total = enrollments.count()
        if total == 0:
            return 0
        completed = enrollments.filter(status=Enrollment.Status.COMPLETED).count()
        return round((completed / total) * 100, 2)


class TeacherEarningsView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]

    def get(self, request):
        teacher_account = get_object_or_404(TeacherAccount, client=request.user)

        if not hasattr(teacher_account, 'earnings') or not teacher_account.earnings:
            return Response({
                "total_earned": 0,
                "pending_payout": 0,
                "last_payout_at": None,
                "payout_schedule": teacher_account.payout_schedule,
                "auto_payout": teacher_account.auto_payout,
            })

        from earning.models import TeacherEarning
        earning = teacher_account.earnings

        return Response({
            "total_earned": earning.total_earned,
            "pending_payout": earning.pending_payout,
            "last_payout_at": earning.last_payout_at,
            "payout_schedule": teacher_account.payout_schedule,
            "auto_payout": teacher_account.auto_payout,
            "stripe_account_id": teacher_account.stripe_account_id,
        })