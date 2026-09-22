from django.db import models
from django.utils import timezone
from django.db.models import Avg, Sum, F
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import (
    Category, Course, CourseTeacher, Section, Lecture,
    Enrollment, Review, Question, Answer,
    LectureProgress, CourseAttachment
)
from .serializers import (
    CategorySerializer, CourseListSerializer, CourseDetailSerializer,
    CourseCreateUpdateSerializer, SectionCreateUpdateSerializer,
    LectureCreateUpdateSerializer, EnrollmentSerializer,
    EnrollmentCreateSerializer, ReviewSerializer, ReviewCreateSerializer,
    AnnouncementSerializer, QuestionSerializer, QuestionCreateSerializer,
    AnswerSerializer, LectureProgressSerializer, LectureProgressUpdateSerializer,
    CourseAttachmentSerializer, CourseStatsSerializer
)
from .permissions import (
    IsTeacherOrReadOnly, IsEnrolledOrTeacher, IsStudentOrReadOnly, CanManageEnrollment
)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related('children')
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'name']


class CourseViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'subtitle', 'description', 'category__name']
    ordering_fields = ['created_at', 'published_at', 'total_students', 'average_rating', 'price']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = Course.objects.select_related('category', 'subcategory').prefetch_related(
            'course_teachers__teacher', 'course_teachers__teacher__teacher_account'
        )

        if self.action == 'list':
            if user.is_authenticated and user.role == user.Role.TEACHER:
                return queryset.filter(course_teachers__teacher=user, course_teachers__is_active=True).distinct()
            if user.is_authenticated and user.is_staff:
                return queryset
            return queryset.filter(status=Course.Status.PUBLISHED)

        if self.action in ['retrieve', 'enroll', 'progress', 'announcements', 'questions', 'reviews']:
            if user.is_authenticated and (user.is_staff or user.role == user.Role.TEACHER):
                return queryset
            return queryset.filter(status=Course.Status.PUBLISHED)

        return queryset.filter(course_teachers__teacher=user, course_teachers__is_active=True).distinct()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CourseCreateUpdateSerializer
        if self.action == 'retrieve':
            return CourseDetailSerializer
        return CourseListSerializer

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'destroy', 'publish', 'unpublish']:
            return [IsAuthenticated(), IsTeacherOrReadOnly()]
        if self.action in ['enroll', 'progress', 'complete_lecture']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def perform_create(self, serializer):
        course = serializer.save()
        CourseTeacher.objects.create(
            course=course,
            teacher=self.request.user,
            role=CourseTeacher.Role.PRIMARY,
            revenue_share=100
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsTeacherOrReadOnly])
    def publish(self, request, pk=None):
        course = self.get_object()
        if course.status == Course.Status.PUBLISHED:
            return Response({'detail': 'Course is already published.'}, status=status.HTTP_400_BAD_REQUEST)

        course.status = Course.Status.PUBLISHED
        course.published_at = timezone.now()
        course.total_lectures = Lecture.objects.filter(
            section__course=course, status=Lecture.Status.PUBLISHED
        ).count()
        course.total_duration_minutes = Lecture.objects.filter(
            section__course=course, status=Lecture.Status.PUBLISHED
        ).aggregate(total=Sum('video_duration'))['total'] or 0
        course.total_duration_minutes //= 60
        course.save()
        return Response(CourseDetailSerializer(course, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsTeacherOrReadOnly])
    def unpublish(self, request, pk=None):
        course = self.get_object()
        course.status = Course.Status.DRAFT
        course.save()
        return Response(CourseDetailSerializer(course, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def enroll(self, request, pk=None):
        course = self.get_object()
        user = request.user

        if user.role != user.Role.STUDENT:
            return Response({'detail': 'Only students can enroll in courses.'}, status=status.HTTP_403_FORBIDDEN)

        if Enrollment.objects.filter(student=user, course=course).exists():
            return Response({'detail': 'Already enrolled in this course.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = EnrollmentCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        enrollment = serializer.save(course=course)

        course.total_students = F('total_students') + 1
        course.save(update_fields=['total_students'])

        return Response(EnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsEnrolledOrTeacher])
    def progress(self, request, pk=None):
        course = self.get_object()
        user = request.user

        if user.role == user.Role.STUDENT:
            enrollment = Enrollment.objects.filter(student=user, course=course).first()
            if not enrollment:
                return Response({'detail': 'Not enrolled in this course.'}, status=status.HTTP_404_NOT_FOUND)

            progress_data = {
                'enrollment': EnrollmentSerializer(enrollment).data,
                'completed_lectures': enrollment.completed_lectures.count(),
                'total_lectures': Lecture.objects.filter(section__course=course, status=Lecture.Status.PUBLISHED).count(),
                'lecture_progress': LectureProgressSerializer(
                    LectureProgress.objects.filter(enrollment=enrollment), many=True
                ).data
            }
            return Response(progress_data)

        enrollments = Enrollment.objects.filter(course=course, status=Enrollment.Status.ACTIVE).select_related('student')
        return Response(EnrollmentSerializer(enrollments, many=True).data)

    @action(detail=True, methods=['post'], url_path='lectures/(?P<lecture_id>[^/.]+)/complete', permission_classes=[IsAuthenticated, IsEnrolledOrTeacher])
    def complete_lecture(self, request, pk=None, lecture_id=None):
        course = self.get_object()
        user = request.user

        if user.role != user.Role.STUDENT:
            return Response({'detail': 'Only students can mark lectures as complete.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            lecture = Lecture.objects.get(pk=lecture_id, section__course=course, status=Lecture.Status.PUBLISHED)
        except Lecture.DoesNotExist:
            return Response({'detail': 'Lecture not found.'}, status=status.HTTP_404_NOT_FOUND)

        enrollment = Enrollment.objects.filter(student=user, course=course, status=Enrollment.Status.ACTIVE).first()
        if not enrollment:
            return Response({'detail': 'Not enrolled in this course.'}, status=status.HTTP_404_NOT_FOUND)

        progress, _ = LectureProgress.objects.get_or_create(enrollment=enrollment, lecture=lecture)
        progress.is_completed = True
        progress.completed_at = timezone.now()
        progress.watch_time = lecture.video_duration
        progress.last_position = lecture.video_duration
        progress.save()

        enrollment.completed_lectures.add(lecture)
        total_lectures = Lecture.objects.filter(section__course=course, status=Lecture.Status.PUBLISHED).count()
        completed_count = enrollment.completed_lectures.count()
        if total_lectures > 0:
            enrollment.progress_percentage = round((completed_count / total_lectures) * 100, 2)
            if enrollment.progress_percentage >= 100:
                enrollment.status = Enrollment.Status.COMPLETED
                enrollment.completed_at = timezone.now()
            enrollment.save()

        return Response(LectureProgressSerializer(progress).data)

    @action(detail=True, methods=['get', 'post'], permission_classes=[IsAuthenticated, IsEnrolledOrTeacher])
    def announcements(self, request, pk=None):
        course = self.get_object()

        if request.method == 'GET':
            announcements = course.announcements.filter(is_published=True).select_related('teacher')
            return Response(AnnouncementSerializer(announcements, many=True).data)

        if request.user.role != request.user.Role.TEACHER:
            return Response({'detail': 'Only teachers can create announcements.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(course=course, teacher=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], permission_classes=[IsAuthenticated, IsEnrolledOrTeacher])
    def questions(self, request, pk=None):
        course = self.get_object()

        if request.method == 'GET':
            questions = course.questions.select_related('student', 'lecture').prefetch_related('answers__teacher')
            return Response(QuestionSerializer(questions, many=True).data)

        serializer = QuestionCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(student=request.user, course=course)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def reviews(self, request, pk=None):
        course = self.get_object()
        reviews = course.enrollments.filter(review__isnull=False).select_related('review', 'student')
        serializer = ReviewSerializer([e.review for e in reviews], many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_courses(self, request):
        user = request.user

        if user.role == user.Role.TEACHER:
            courses = self.get_queryset()
        elif user.role == user.Role.STUDENT:
            enrollments = Enrollment.objects.filter(student=user).select_related('course')
            courses = Course.objects.filter(enrollments__student=user).distinct()
        else:
            courses = Course.objects.none()

        serializer = CourseListSerializer(courses, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def stats(self, request):
        if not request.user.is_staff:
            return Response({'detail': 'Admin only.'}, status=status.HTTP_403_FORBIDDEN)

        stats = {
            'total_courses': Course.objects.count(),
            'published_courses': Course.objects.filter(status=Course.Status.PUBLISHED).count(),
            'draft_courses': Course.objects.filter(status=Course.Status.DRAFT).count(),
            'total_students': Enrollment.objects.filter(status=Enrollment.Status.ACTIVE).count(),
            'total_revenue': Enrollment.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
            'average_rating': Review.objects.aggregate(avg=Avg('rating'))['avg'] or 0,
        }
        serializer = CourseStatsSerializer(stats)
        return Response(serializer.data)


class SectionViewSet(viewsets.ModelViewSet):
    serializer_class = SectionCreateUpdateSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrReadOnly]

    def get_queryset(self):
        course_id = self.kwargs.get('course_pk')
        return Section.objects.filter(course_id=course_id).order_by('order')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['course_id'] = self.kwargs.get('course_pk')
        return context

    def perform_create(self, serializer):
        course = Course.objects.get(pk=self.kwargs.get('course_pk'))
        max_order = Section.objects.filter(course=course).aggregate(max_order=models.Max('order'))['max_order'] or 0
        serializer.save(course=course, order=max_order + 1)

    @action(detail=True, methods=['post'])
    def reorder(self, request, course_pk=None, pk=None):
        section = self.get_object()
        new_order = request.data.get('order')
        if new_order is None:
            return Response({'detail': 'Order is required.'}, status=status.HTTP_400_BAD_REQUEST)

        Section.objects.filter(course_id=course_pk, order__gte=new_order).exclude(pk=section.pk).update(order=F('order') + 1)
        section.order = new_order
        section.save()
        return Response(SectionCreateUpdateSerializer(section).data)


class LectureViewSet(viewsets.ModelViewSet):
    serializer_class = LectureCreateUpdateSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        section_id = self.kwargs.get('section_pk')
        return Lecture.objects.filter(section_id=section_id).order_by('order')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['section_id'] = self.kwargs.get('section_pk')
        return context

    def perform_create(self, serializer):
        section = Section.objects.get(pk=self.kwargs.get('section_pk'))
        max_order = Lecture.objects.filter(section=section).aggregate(max_order=models.Max('order'))['max_order'] or 0
        serializer.save(section=section, order=max_order + 1)

    @action(detail=True, methods=['post'])
    def reorder(self, request, section_pk=None, pk=None):
        lecture = self.get_object()
        new_order = request.data.get('order')
        if new_order is None:
            return Response({'detail': 'Order is required.'}, status=status.HTTP_400_BAD_REQUEST)

        Lecture.objects.filter(section_id=section_pk, order__gte=new_order).exclude(pk=lecture.pk).update(order=F('order') + 1)
        lecture.order = new_order
        lecture.save()
        return Response(LectureCreateUpdateSerializer(lecture).data)


class EnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated, CanManageEnrollment]

    def get_queryset(self):
        user = self.request.user
        if user.role == user.Role.STUDENT:
            return Enrollment.objects.filter(student=user).select_related('course', 'course__category')
        elif user.role == user.Role.TEACHER:
            return Enrollment.objects.filter(course__course_teachers__teacher=user, course__course_teachers__is_active=True).select_related('student', 'course')
        return Enrollment.objects.none()

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsStudentOrReadOnly])
    def drop(self, request, pk=None):
        enrollment = self.get_object()
        if enrollment.status != Enrollment.Status.ACTIVE:
            return Response({'detail': 'Can only drop active enrollments.'}, status=status.HTTP_400_BAD_REQUEST)
        enrollment.status = Enrollment.Status.DROPPED
        enrollment.save()
        return Response(EnrollmentSerializer(enrollment).data)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related('enrollment__student', 'enrollment__course')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == user.Role.STUDENT:
            return self.queryset.filter(enrollment__student=user)
        elif user.role == user.Role.TEACHER:
            return self.queryset.filter(enrollment__course__course_teachers__teacher=user, enrollment__course__course_teachers__is_active=True)
        return self.queryset

    def perform_create(self, serializer):
        serializer.save()


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated, IsEnrolledOrTeacher]

    def get_queryset(self):
        course_id = self.kwargs.get('course_pk')
        return Question.objects.filter(course_id=course_id).select_related('student', 'lecture').prefetch_related('answers__teacher')

    def get_serializer_class(self):
        if self.action == 'create':
            return QuestionCreateSerializer
        return QuestionSerializer

    def perform_create(self, serializer):
        course = Course.objects.get(pk=self.kwargs.get('course_pk'))
        serializer.save(student=self.request.user, course=course)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def answer(self, request, course_pk=None, pk=None):
        question = self.get_object()
        if request.user.role != request.user.Role.TEACHER:
            return Response({'detail': 'Only teachers can answer questions.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(question=question, teacher=request.user)
        question.is_answered = True
        question.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AnswerViewSet(viewsets.ModelViewSet):
    serializer_class = AnswerSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrReadOnly]

    def get_queryset(self):
        question_id = self.kwargs.get('question_pk')
        return Answer.objects.filter(question_id=question_id)

    def perform_create(self, serializer):
        question = Question.objects.get(pk=self.kwargs.get('question_pk'))
        serializer.save(question=question, teacher=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def accept(self, request, question_pk=None, pk=None):
        answer = self.get_object()
        if answer.question.course.course_teachers.filter(teacher=request.user, is_active=True).exists():
            answer.is_accepted = True
            answer.save()
            answer.question.is_answered = True
            answer.question.save()
            return Response(AnswerSerializer(answer).data)
        return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)


class LectureProgressViewSet(viewsets.ModelViewSet):
    serializer_class = LectureProgressSerializer
    permission_classes = [IsAuthenticated, IsEnrolledOrTeacher]

    def get_queryset(self):
        enrollment_id = self.kwargs.get('enrollment_pk')
        return LectureProgress.objects.filter(enrollment_id=enrollment_id)

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return LectureProgressUpdateSerializer
        return LectureProgressSerializer

    def perform_create(self, serializer):
        enrollment = Enrollment.objects.get(pk=self.kwargs.get('enrollment_pk'))
        serializer.save(enrollment=enrollment)


class CourseAttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = CourseAttachmentSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        course_id = self.kwargs.get('course_pk')
        return CourseAttachment.objects.filter(course_id=course_id)

    def perform_create(self, serializer):
        course = Course.objects.get(pk=self.kwargs.get('course_pk'))
        file_obj = serializer.validated_data['file']
        serializer.save(
            course=course,
            file_size=file_obj.size,
            file_type=file_obj.content_type
        )