from rest_framework import serializers
from django.db.models import Avg, Count

from certificate.models import Certificate, CertificateTemplate
from .models import (
    QuestionBank, Assessment, AssessmentQuestion,
    Attempt, Answer, Rubric, RubricCriterion, RubricLevel, RubricScore,
    PeerReview
)
from client.serializers import PublicProfileSerializer
from course.serializers import CourseListSerializer


class QuestionBankSerializer(serializers.ModelSerializer):
    creator = PublicProfileSerializer(read_only=True)
    usage_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = QuestionBank
        fields = [
            'id', 'title', 'question_type', 'difficulty', 'content', 'content_html',
            'explanation', 'explanation_html', 'points', 'time_limit',
            'options', 'correct_answer', 'left_items', 'right_items',
            'starter_code', 'solution_code', 'test_cases', 'language',
            'tags', 'learning_objectives', 'creator', 'is_public',
            'course', 'usage_count', 'avg_difficulty_rating',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'creator', 'usage_count', 'avg_difficulty_rating', 'created_at', 'updated_at']


class QuestionBankCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionBank
        fields = [
            'title', 'question_type', 'difficulty', 'content', 'explanation',
            'points', 'time_limit', 'options', 'correct_answer',
            'left_items', 'right_items', 'starter_code', 'solution_code',
            'test_cases', 'language', 'tags', 'learning_objectives',
            'is_public', 'course'
        ]

    def create(self, validated_data):
        validated_data['creator'] = self.context['request'].user
        return super().create(validated_data)


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    question = QuestionBankSerializer(read_only=True)
    question_id = serializers.UUIDField(write_only=True)
    effective_points = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentQuestion
        fields = ['id', 'question', 'question_id', 'order', 'points_override', 'effective_points']

    def get_effective_points(self, obj):
        return obj.points_override if obj.points_override else obj.question.points


class AssessmentListSerializer(serializers.ModelSerializer):
    course = CourseListSerializer(read_only=True)
    question_count = serializers.SerializerMethodField()
    attempt_count = serializers.SerializerMethodField()
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = Assessment
        fields = [
            'id', 'title', 'slug', 'description', 'assessment_type', 'status',
            'grading_type', 'course', 'section', 'lecture',
            'time_limit', 'available_from', 'available_until',
            'max_attempts', 'passing_score', 'total_points',
            'question_count', 'attempt_count', 'is_available',
            'created_at', 'published_at'
        ]

    def get_question_count(self, obj):
        return obj.questions.count()

    def get_attempt_count(self, obj):
        return obj.attempts.count()


class AssessmentDetailSerializer(AssessmentListSerializer):
    questions = AssessmentQuestionSerializer(source='assessmentquestion_set', many=True, read_only=True)
    prerequisite_assessments = AssessmentListSerializer(many=True, read_only=True)
    rubric = serializers.SerializerMethodField()

    class Meta(AssessmentListSerializer.Meta):
        fields = AssessmentListSerializer.Meta.fields + [
            'instructions', 'questions', 'randomize_questions', 'randomize_options',
            'questions_per_attempt', 'allow_late_submission', 'late_penalty_percent',
            'show_correct_answers', 'show_explanations', 'show_score_immediately',
            'allow_review', 'require_proctoring', 'proctoring_settings',
            'prerequisite_assessments', 'rubric', 'created_by', 'updated_at'
        ]

    def get_rubric(self, obj):
        if hasattr(obj, 'rubric'):
            return RubricSerializer(obj.rubric).data
        return None


class AssessmentCreateUpdateSerializer(serializers.ModelSerializer):
    questions = serializers.ListField(
        child=serializers.DictField(child=serializers.UUIDField()),
        required=False,
        write_only=True
    )

    class Meta:
        model = Assessment
        fields = [
            'id', 'title', 'slug', 'description', 'instructions',
            'assessment_type', 'grading_type', 'course', 'section', 'lecture',
            'questions', 'randomize_questions', 'randomize_options',
            'questions_per_attempt', 'time_limit', 'available_from', 'available_until',
            'allow_late_submission', 'late_penalty_percent', 'max_attempts',
            'passing_score', 'show_correct_answers', 'show_explanations',
            'show_score_immediately', 'allow_review', 'require_proctoring',
            'proctoring_settings', 'prerequisite_assessments'
        ]
        read_only_fields = ['id', 'slug', 'total_points', 'created_by', 'created_at', 'updated_at', 'published_at']

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        validated_data['created_by'] = self.context['request'].user
        assessment = Assessment.objects.create(**validated_data)
        self._set_questions(assessment, questions_data)
        return assessment

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if questions_data is not None:
            self._set_questions(instance, questions_data)
        return instance

    def _set_questions(self, assessment, questions_data):
        AssessmentQuestion.objects.filter(assessment=assessment).delete()
        for i, q_data in enumerate(questions_data):
            question_id = q_data.get('question_id') or q_data.get('id')
            points_override = q_data.get('points_override')
            if question_id:
                AssessmentQuestion.objects.create(
                    assessment=assessment,
                    question_id=question_id,
                    order=i,
                    points_override=points_override
                )
        assessment.total_points = sum(
            aq.points_override or aq.question.points
            for aq in assessment.assessmentquestion_set.all()
        )
        assessment.save(update_fields=['total_points'])


class AnswerSerializer(serializers.ModelSerializer):
    question = QuestionBankSerializer(read_only=True)

    class Meta:
        model = Answer
        fields = [
            'id', 'question', 'response', 'response_text', 'response_files',
            'is_correct', 'points_earned', 'max_points',
            'feedback', 'graded_by', 'graded_at',
            'auto_graded', 'grading_details',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'question', 'is_correct', 'points_earned',
                           'feedback', 'graded_by', 'graded_at',
                           'auto_graded', 'grading_details', 'created_at', 'updated_at']


class AnswerSubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['question', 'response', 'response_text', 'response_files']


class AttemptSerializer(serializers.ModelSerializer):
    answers = AnswerSerializer(many=True, read_only=True)
    assessment = AssessmentListSerializer(read_only=True)
    student = PublicProfileSerializer(read_only=True)

    class Meta:
        model = Attempt
        fields = [
            'id', 'assessment', 'student', 'attempt_number', 'status',
            'started_at', 'submitted_at', 'graded_at', 'time_spent',
            'earned_points', 'total_points', 'score_percentage', 'is_passed',
            'graded_by', 'grading_notes', 'flagged_for_review',
            'answers', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'assessment', 'student', 'attempt_number', 'status',
            'started_at', 'submitted_at', 'graded_at',
            'earned_points', 'total_points', 'score_percentage', 'is_passed',
            'graded_by', 'grading_notes', 'flagged_for_review',
            'created_at', 'updated_at'
        ]


class AttemptStartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attempt
        fields = ['id', 'assessment', 'attempt_number', 'started_at', 'status']
        read_only_fields = fields


class AttemptSubmitSerializer(serializers.Serializer):
    answers = serializers.ListField(child=serializers.DictField())
    time_spent = serializers.IntegerField(required=False, default=0)


class AttemptGradeSerializer(serializers.Serializer):
    answers = serializers.ListField(child=serializers.DictField())
    grading_notes = serializers.CharField(required=False, allow_blank=True)


class RubricLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = RubricLevel
        fields = ['id', 'name', 'description', 'points', 'order']


class RubricCriterionSerializer(serializers.ModelSerializer):
    levels = RubricLevelSerializer(many=True, read_only=True)

    class Meta:
        model = RubricCriterion
        fields = ['id', 'name', 'description', 'points', 'order', 'levels']


class RubricSerializer(serializers.ModelSerializer):
    criteria = RubricCriterionSerializer(many=True, read_only=True)

    class Meta:
        model = Rubric
        fields = ['id', 'name', 'description', 'total_points', 'criteria', 'created_at', 'updated_at']


class RubricCreateSerializer(serializers.ModelSerializer):
    criteria = serializers.ListField(child=serializers.DictField(), write_only=True)

    class Meta:
        model = Rubric
        fields = ['name', 'description', 'criteria']

    def create(self, validated_data):
        criteria_data = validated_data.pop('criteria')
        rubric = Rubric.objects.create(**validated_data)
        total = 0
        for c_data in criteria_data:
            levels_data = c_data.pop('levels', [])
            criterion = RubricCriterion.objects.create(rubric=rubric, **c_data)
            total += criterion.points
            for l_data in levels_data:
                RubricLevel.objects.create(criterion=criterion, **l_data)
        rubric.total_points = total
        rubric.save()
        return rubric


class RubricScoreSerializer(serializers.ModelSerializer):
    criterion_name = serializers.CharField(source='criterion.name', read_only=True)
    level_name = serializers.CharField(source='level.name', read_only=True)
    max_points = serializers.IntegerField(source='level.points', read_only=True)

    class Meta:
        model = RubricScore
        fields = ['id', 'criterion', 'criterion_name', 'level', 'level_name',
                  'points_earned', 'max_points', 'feedback', 'graded_by', 'graded_at']


class PeerReviewSerializer(serializers.ModelSerializer):
    reviewer = PublicProfileSerializer(read_only=True)
    submission_student = PublicProfileSerializer(source='submission.student', read_only=True)

    class Meta:
        model = PeerReview
        fields = [
            'id', 'assessment', 'submission', 'reviewer', 'submission_student',
            'status', 'assigned_at', 'started_at', 'submitted_at',
            'overall_feedback', 'score_given', 'rubric_scores',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reviewer', 'assigned_at', 'submitted_at', 'created_at', 'updated_at']


class PeerReviewSubmitSerializer(serializers.Serializer):
    overall_feedback = serializers.CharField(required=False, allow_blank=True)
    score_given = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    rubric_scores = serializers.DictField(child=serializers.IntegerField(), required=False)


class CertificateSerializer(serializers.ModelSerializer):
    student = PublicProfileSerializer(read_only=True)
    course = CourseListSerializer(read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'id', 'student', 'course', 'assessment', 'certificate_id',
            'title', 'description', 'status', 'issued_at', 'expires_at',
            'template_name', 'pdf_file', 'verification_url',
            'credential_id', 'blockchain_tx_hash', 'metadata'
        ]
        read_only_fields = fields


class CertificateTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateTemplate
        fields = ['id', 'name', 'description', 'html_template', 'css_styles',
                  'width', 'height', 'available_variables', 'is_default', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class CertificateVerifySerializer(serializers.Serializer):
    certificate_id = serializers.CharField()
    credential_id = serializers.CharField(required=False)

    def validate(self, attrs):
        cert_id = attrs.get('certificate_id')
        cred_id = attrs.get('credential_id')

        if not cert_id and not cred_id:
            raise serializers.ValidationError("Either certificate_id or credential_id is required.")

        query = Certificate.objects.all()
        if cert_id:
            query = query.filter(certificate_id=cert_id)
        if cred_id:
            query = query.filter(credential_id=cred_id)

        if not query.exists():
            raise serializers.ValidationError("Certificate not found.")

        certificate = query.first()
        if certificate.status != Certificate.Status.ISSUED:
            raise serializers.ValidationError("Certificate is not valid.")

        attrs['certificate'] = certificate
        return attrs