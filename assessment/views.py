from django.db.models import Avg, Count, Q, F
from rest_framework.decorators import action
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404

from .models import (
    QuestionBank, Assessment, AssessmentQuestion,
    Attempt, Answer, Rubric, RubricCriterion, RubricLevel, RubricScore,
    PeerReview
)
from .serializers import (
    QuestionBankSerializer, QuestionBankCreateSerializer,
    AssessmentListSerializer, AssessmentDetailSerializer, AssessmentCreateUpdateSerializer,
    AttemptSerializer, AttemptStartSerializer, AttemptSubmitSerializer, AttemptGradeSerializer,
    AnswerSerializer, AnswerSubmitSerializer,
    RubricSerializer, RubricCreateSerializer, RubricScoreSerializer,
    PeerReviewSerializer, PeerReviewSubmitSerializer,
)
from client.permissions import IsAccountOwnerOrStaff
from course.models import Course, Enrollment, CourseTeacher


class QuestionBankViewSet(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'tags', 'learning_objectives']
    ordering_fields = ['created_at', 'difficulty', 'usage_count']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return QuestionBank.objects.all()
        return QuestionBank.objects.filter(
            Q(creator=user) | Q(is_public=True) | Q(course__course_teachers__teacher=user, course__course_teachers__is_active=True)
        ).distinct()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return QuestionBankCreateSerializer
        return QuestionBankSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Filters
        q_type = request.query_params.get('type')
        if q_type:
            queryset = queryset.filter(question_type=q_type)

        difficulty = request.query_params.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        course_id = request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        if instance.creator != request.user and not request.user.is_staff:
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.creator != request.user and not request.user.is_staff:
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssessmentViewSet(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'published_at', 'assessment_type']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        base = Assessment.objects.select_related('course', 'section', 'lecture', 'created_by').prefetch_related('questions')

        if self.action == 'list':
            if user.is_staff:
                return base
            if user.role == user.Role.TEACHER:
                return base.filter(course__course_teachers__teacher=user, course__course_teachers__is_active=True).distinct()
            # Student - only published assessments in enrolled courses
            enrolled_courses = Enrollment.objects.filter(
                student=user, status=Enrollment.Status.ACTIVE
            ).values_list('course_id', flat=True)
            return base.filter(course_id__in=enrolled_courses, status=Assessment.Status.PUBLISHED)

        if self.action in ['retrieve', 'start', 'submit', 'results']:
            if user.is_staff or user.role == user.Role.TEACHER:
                return base
            enrolled_courses = Enrollment.objects.filter(
                student=user, status=Enrollment.Status.ACTIVE
            ).values_list('course_id', flat=True)
            return base.filter(course_id__in=enrolled_courses)

        return base.filter(created_by=user)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AssessmentCreateUpdateSerializer
        if self.action == 'retrieve':
            return AssessmentDetailSerializer
        return AssessmentListSerializer

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'destroy', 'publish', 'duplicate']:
            return [IsAuthenticated()]
        if self.action in ['start', 'submit', 'results', 'my_attempts']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Filters
        a_type = request.query_params.get('type')
        if a_type:
            queryset = queryset.filter(assessment_type=a_type)

        course_id = request.query_params.get('course')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        if instance.created_by != request.user and not request.user.is_staff:
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.created_by != request.user and not request.user.is_staff:
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def publish(self, request, *args, **kwargs):
        assessment = self.get_object()
        if assessment.created_by != request.user and not request.user.is_staff:
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)

        if assessment.status == Assessment.Status.PUBLISHED:
            return Response({'detail': 'Already published.'}, status=status.HTTP_400_BAD_REQUEST)

        assessment.status = Assessment.Status.PUBLISHED
        assessment.published_at = timezone.now()
        assessment.save(update_fields=['status', 'published_at'])
        return Response(AssessmentDetailSerializer(assessment, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def duplicate(self, request, *args, **kwargs):
        assessment = self.get_object()
        new_assessment = Assessment.objects.create(
            title=f"{assessment.title} (Copy)",
            description=assessment.description,
            instructions=assessment.instructions,
            assessment_type=assessment.assessment_type,
            grading_type=assessment.grading_type,
            course=assessment.course,
            section=assessment.section,
            lecture=assessment.lecture,
            time_limit=assessment.time_limit,
            max_attempts=assessment.max_attempts,
            passing_score=assessment.passing_score,
            show_correct_answers=assessment.show_correct_answers,
            show_explanations=assessment.show_explanations,
            show_score_immediately=assessment.show_score_immediately,
            allow_review=assessment.allow_review,
            require_proctoring=assessment.require_proctoring,
            proctoring_settings=assessment.proctoring_settings,
            created_by=request.user,
            status=Assessment.Status.DRAFT
        )
        # Copy questions
        for aq in assessment.assessmentquestion_set.all():
            AssessmentQuestion.objects.create(
                assessment=new_assessment,
                question=aq.question,
                order=aq.order,
                points_override=aq.points_override
            )
        new_assessment.total_points = assessment.total_points
        new_assessment.save()
        return Response(AssessmentDetailSerializer(new_assessment, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def start(self, request, *args, **kwargs):
        assessment = self.get_object()

        if not assessment.is_available:
            return Response({'error': 'Assessment is not available.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check prerequisites
        for prereq in assessment.prerequisite_assessments.all():
            passed = Attempt.objects.filter(
                assessment=prereq,
                student=request.user,
                is_passed=True
            ).exists()
            if not passed:
                return Response({'error': f'Prerequisite not met: {prereq.title}'}, status=status.HTTP_400_BAD_REQUEST)

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=assessment.course,
            status=Enrollment.Status.ACTIVE
        ).first()
        if not enrollment:
            return Response({'error': 'Not enrolled in this course.'}, status=status.HTTP_403_FORBIDDEN)

        # Check max attempts
        existing_attempts = Attempt.objects.filter(assessment=assessment, student=request.user).count()
        if existing_attempts >= assessment.max_attempts:
            return Response({'error': 'Maximum attempts reached.'}, status=status.HTTP_400_BAD_REQUEST)

        # Create new attempt
        attempt = Attempt.objects.create(
            assessment=assessment,
            student=request.user,
            enrollment=enrollment,
            attempt_number=existing_attempts + 1,
            status=Attempt.Status.IN_PROGRESS,
            total_points=assessment.total_points,
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        # Generate questions for this attempt
        questions = assessment.questions.all()
        if assessment.randomize_questions:
            questions = questions.order_by('?')
        if assessment.questions_per_attempt > 0:
            questions = questions[:assessment.questions_per_attempt]

        # Create answers
        for aq in questions:
            Answer.objects.create(
                attempt=attempt,
                question=aq.question if isinstance(aq, AssessmentQuestion) else aq,
                assessment_question=aq if isinstance(aq, AssessmentQuestion) else None,
                max_points=aq.points_override or aq.question.points
            )

        return Response(AttemptStartSerializer(attempt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def submit(self, request, *args, **kwargs):
        assessment = self.get_object()

        # Find in-progress attempt
        attempt = Attempt.objects.filter(
            assessment=assessment,
            student=request.user,
            status=Attempt.Status.IN_PROGRESS
        ).order_by('-attempt_number').first()

        if not attempt:
            return Response({'error': 'No active attempt found.'}, status=status.HTTP_400_BAD_REQUEST)

        # Update answers
        answers_data = request.data.get('answers', [])
        time_spent = request.data.get('time_spent', 0)

        for ans_data in answers_data:
            answer_id = ans_data.get('id') or ans_data.get('answer_id')
            question_id = ans_data.get('question_id')

            if answer_id:
                try:
                    answer = Answer.objects.get(id=answer_id, attempt=attempt)
                except Answer.DoesNotExist:
                    continue
            elif question_id:
                try:
                    answer = Answer.objects.get(attempt=attempt, question_id=question_id)
                except Answer.DoesNotExist:
                    continue
            else:
                continue

            answer.response = ans_data.get('response', {})
            answer.response_text = ans_data.get('response_text', '')
            answer.response_files = ans_data.get('response_files', [])
            answer.save()

        # Auto-grade if applicable
        if assessment.grading_type in [Assessment.GradingType.AUTO, Assessment.GradingType.HYBRID]:
            self._auto_grade_attempt(attempt)

        attempt.status = Attempt.Status.SUBMITTED
        attempt.submitted_at = timezone.now()
        attempt.time_spent = time_spent
        attempt.save(update_fields=['status', 'submitted_at', 'time_spent', 'earned_points', 'total_points', 'score_percentage', 'is_passed'])

        return Response(AttemptSerializer(attempt, context={'request': request}).data)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def results(self, request, *args, **kwargs):
        assessment = self.get_object()

        # Get best attempt
        attempt = Attempt.objects.filter(
            assessment=assessment,
            student=request.user,
            status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED]
        ).order_by('-score_percentage').first()

        if not attempt:
            return Response({'error': 'No completed attempt found.'}, status=status.HTTP_404_NOT_FOUND)

        # Check if review is allowed
        if not assessment.allow_review:
            return Response({'error': 'Review not allowed for this assessment.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AttemptSerializer(attempt, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def my_attempts(self, request, *args, **kwargs):
        assessment = self.get_object()
        attempts = Attempt.objects.filter(assessment=assessment, student=request.user)
        serializer = AttemptSerializer(attempts, many=True, context={'request': request})
        return Response(serializer.data)

    def _auto_grade_attempt(self, attempt):
        earned = 0
        for answer in attempt.answers.all():
            question = answer.question
            if question.question_type in [QuestionBank.QuestionType.MULTIPLE_CHOICE, QuestionBank.QuestionType.TRUE_FALSE]:
                is_correct = self._grade_choice(answer, question)
                answer.is_correct = is_correct
                answer.points_earned = answer.max_points if is_correct else 0
                answer.auto_graded = True
                answer.graded_at = timezone.now()
                earned += float(answer.points_earned)
            elif question.question_type == QuestionBank.QuestionType.MULTIPLE_ANSWER:
                is_correct = self._grade_multiple_answer(answer, question)
                answer.is_correct = is_correct
                answer.points_earned = answer.max_points if is_correct else 0
                answer.auto_graded = True
                answer.graded_at = timezone.now()
                earned += float(answer.points_earned)
            elif question.question_type == QuestionBank.QuestionType.FILL_BLANK:
                is_correct = self._grade_fill_blank(answer, question)
                answer.is_correct = is_correct
                answer.points_earned = answer.max_points if is_correct else 0
                answer.auto_graded = True
                answer.graded_at = timezone.now()
                earned += float(answer.points_earned)

        attempt.earned_points = earned
        attempt.calculate_score()

    def _grade_choice(self, answer, question):
        correct = question.correct_answer
        response = answer.response
        if isinstance(correct, dict):
            correct_id = correct.get('option_id')
            return response.get('selected_option') == correct_id
        return response.get('selected_option') == correct

    def _grade_multiple_answer(self, answer, question):
        correct = question.correct_answer
        response = answer.response
        correct_ids = set(correct.get('option_ids', []))
        selected_ids = set(response.get('selected_options', []))
        return correct_ids == selected_ids

    def _grade_fill_blank(self, answer, question):
        correct = question.correct_answer
        response = answer.response
        correct_answers = [c.lower().strip() for c in correct.get('answers', [])]
        user_answer = response.get('answer', '').lower().strip()
        return user_answer in correct_answers

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class AttemptGradeView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AttemptGradeSerializer

    def post(self, request, pk):
        attempt = get_object_or_404(Attempt, pk=pk)

        # Check permission
        if not (request.user.is_staff or attempt.assessment.course.course_teachers.filter(teacher=request.user, is_active=True).exists()):
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        answers_data = serializer.validated_data.get('answers', [])
        grading_notes = serializer.validated_data.get('grading_notes', '')

        earned = 0
        for ans_data in answers_data:
            answer_id = ans_data.get('id')
            try:
                answer = Answer.objects.get(id=answer_id, attempt=attempt)
            except Answer.DoesNotExist:
                continue

            answer.is_correct = ans_data.get('is_correct', False)
            answer.points_earned = ans_data.get('points_earned', 0)
            answer.feedback = ans_data.get('feedback', '')
            answer.graded_by = request.user
            answer.graded_at = timezone.now()
            answer.auto_graded = False
            answer.save()
            earned += float(answer.points_earned)

        attempt.earned_points = earned
        attempt.graded_by = request.user
        attempt.graded_at = timezone.now()
        attempt.grading_notes = grading_notes
        attempt.status = Attempt.Status.GRADED
        attempt.calculate_score()
        attempt.save(update_fields=['earned_points', 'graded_by', 'graded_at', 'grading_notes', 'status', 'score_percentage', 'is_passed'])

        return Response(AttemptSerializer(attempt, context={'request': request}).data)


class AttemptRubricGradeView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RubricScoreSerializer

    def post(self, request, pk):
        attempt = get_object_or_404(Attempt, pk=pk)

        if not (request.user.is_staff or attempt.assessment.course.course_teachers.filter(teacher=request.user, is_active=True).exists()):
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)

        rubric_scores = request.data.get('rubric_scores', [])
        earned = 0

        for rs_data in rubric_scores:
            criterion_id = rs_data.get('criterion_id')
            level_id = rs_data.get('level_id')
            points = rs_data.get('points_earned', 0)
            feedback = rs_data.get('feedback', '')

            try:
                criterion = RubricCriterion.objects.get(id=criterion_id, rubric__assessment=attempt.assessment)
                level = RubricLevel.objects.get(id=level_id, criterion=criterion)
            except (RubricCriterion.DoesNotExist, RubricLevel.DoesNotExist):
                continue

            RubricScore.objects.update_or_create(
                attempt=attempt,
                criterion=criterion,
                defaults={
                    'level': level,
                    'points_earned': points,
                    'feedback': feedback,
                    'graded_by': request.user
                }
            )
            earned += points

        attempt.earned_points = earned
        attempt.graded_by = request.user
        attempt.graded_at = timezone.now()
        attempt.status = Attempt.Status.GRADED
        attempt.calculate_score()
        attempt.save()

        return Response(AttemptSerializer(attempt, context={'request': request}).data)


class PeerReviewViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PeerReview.objects.filter(reviewer=self.request.user)

    def get_serializer_class(self):
        if self.action == 'submit':
            return PeerReviewSubmitSerializer
        return PeerReviewSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset().select_related('submission__student', 'assessment')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk):
        review = get_object_or_404(PeerReview, pk=pk, reviewer=request.user)
        if review.status != PeerReview.Status.ASSIGNED:
            return Response({'error': 'Review already started.'}, status=status.HTTP_400_BAD_REQUEST)
        review.status = PeerReview.Status.IN_PROGRESS
        review.started_at = timezone.now()
        review.save()
        return Response(PeerReviewSerializer(review).data)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk):
        review = get_object_or_404(PeerReview, pk=pk, reviewer=request.user)
        if review.status == PeerReview.Status.SUBMITTED:
            return Response({'error': 'Already submitted.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review.overall_feedback = serializer.validated_data.get('overall_feedback', '')
        review.score_given = serializer.validated_data.get('score_given')
        review.rubric_scores = serializer.validated_data.get('rubric_scores', {})
        review.status = PeerReview.Status.SUBMITTED
        review.submitted_at = timezone.now()
        review.save()

        return Response(PeerReviewSerializer(review).data)

