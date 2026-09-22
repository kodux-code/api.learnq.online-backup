from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class QuestionBank(models.Model):
    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = 'multiple_choice', 'Multiple Choice'
        MULTIPLE_ANSWER = 'multiple_answer', 'Multiple Answer'
        TRUE_FALSE = 'true_false', 'True/False'
        SHORT_ANSWER = 'short_answer', 'Short Answer'
        ESSAY = 'essay', 'Essay'
        FILL_BLANK = 'fill_blank', 'Fill in the Blank'
        MATCHING = 'matching', 'Matching'
        ORDERING = 'ordering', 'Ordering'
        CODE = 'code', 'Code'
        FILE_UPLOAD = 'file_upload', 'File Upload'

    class Difficulty(models.TextChoices):
        EASY = 'easy', 'Easy'
        MEDIUM = 'medium', 'Medium'
        HARD = 'hard', 'Hard'

    title = models.CharField(max_length=300)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices, default=Difficulty.MEDIUM)

    content = models.TextField()
    content_html = models.TextField(blank=True)

    explanation = models.TextField(blank=True)
    explanation_html = models.TextField(blank=True)

    points = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    time_limit = models.IntegerField(default=0, help_text="Seconds, 0 = no limit")

    # Options for choice questions (JSON)
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.JSONField(default=dict, blank=True)

    # Matching/Ordering
    left_items = models.JSONField(default=list, blank=True)
    right_items = models.JSONField(default=list, blank=True)

    # Code questions
    starter_code = models.TextField(blank=True)
    solution_code = models.TextField(blank=True)
    test_cases = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=20, blank=True)

    # Tags for categorization
    tags = models.JSONField(default=list, blank=True)
    learning_objectives = models.JSONField(default=list, blank=True)

    # Ownership
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_questions')
    is_public = models.BooleanField(default=False)
    course = models.ForeignKey('course.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='question_bank')

    usage_count = models.IntegerField(default=0)
    avg_difficulty_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['question_type', 'difficulty']),
            models.Index(fields=['creator', 'is_public']),
            models.Index(fields=['course']),
        ]

    def __str__(self):
        return f"{self.title} ({self.question_type})"


class Assessment(models.Model):
    class Type(models.TextChoices):
        QUIZ = 'quiz', 'Quiz'
        EXAM = 'exam', 'Exam'
        ASSIGNMENT = 'assignment', 'Assignment'
        PRACTICE = 'practice', 'Practice Test'
        SURVEY = 'survey', 'Survey'
        PEER_REVIEW = 'peer_review', 'Peer Review'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    class GradingType(models.TextChoices):
        AUTO = 'auto', 'Auto-graded'
        MANUAL = 'manual', 'Manual'
        HYBRID = 'hybrid', 'Hybrid'

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=320)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)

    assessment_type = models.CharField(max_length=20, choices=Type.choices, default=Type.QUIZ)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    grading_type = models.CharField(max_length=20, choices=GradingType.choices, default=GradingType.AUTO)

    course = models.ForeignKey('course.Course', on_delete=models.CASCADE, related_name='assessments')
    section = models.ForeignKey('course.Section', on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments')
    lecture = models.ForeignKey('course.Lecture', on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments')

    # Questions
    questions = models.ManyToManyField(QuestionBank, through='AssessmentQuestion', related_name='assessments')
    randomize_questions = models.BooleanField(default=False)
    randomize_options = models.BooleanField(default=False)
    questions_per_attempt = models.IntegerField(default=0, help_text="0 = all questions")

    # Timing
    time_limit = models.IntegerField(default=0, help_text="Minutes, 0 = no limit")
    available_from = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)
    allow_late_submission = models.BooleanField(default=False)
    late_penalty_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Attempts
    max_attempts = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Grading
    total_points = models.IntegerField(default=0)
    show_correct_answers = models.BooleanField(default=True)
    show_explanations = models.BooleanField(default=True)
    show_score_immediately = models.BooleanField(default=True)
    allow_review = models.BooleanField(default=True)

    # Proctoring
    require_proctoring = models.BooleanField(default=False)
    proctoring_settings = models.JSONField(default=dict, blank=True)

    # Prerequisites
    prerequisite_assessments = models.ManyToManyField('self', symmetrical=False, blank=True)

    # Certificate template for auto-issuance on pass
    certificate_template = models.ForeignKey(
        'certificate.CertificateTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assessments'
    )

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_assessments')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['course', 'slug']
        indexes = [
            models.Index(fields=['course', 'status']),
            models.Index(fields=['status', 'available_from']),
            models.Index(fields=['assessment_type']),
        ]

    def __str__(self):
        return f"{self.title} ({self.assessment_type})"

    def save(self, *args, **kwargs):
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def is_available(self):
        now = timezone.now()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until and not self.allow_late_submission:
            return False
        return self.status == self.Status.PUBLISHED


class AssessmentQuestion(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    question = models.ForeignKey(QuestionBank, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    points_override = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])

    class Meta:
        unique_together = ('assessment', 'question')
        ordering = ['order']

    def __str__(self):
        return f"{self.assessment.title} - Q{self.order}: {self.question.title}"


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUBMITTED = 'submitted', 'Submitted'
        GRADED = 'graded', 'Graded'
        ABANDONED = 'abandoned', 'Abandoned'
        EXPIRED = 'expired', 'Expired'

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assessment_attempts')
    enrollment = models.ForeignKey('course.Enrollment', on_delete=models.CASCADE, related_name='assessment_attempts')

    attempt_number = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)

    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    time_spent = models.IntegerField(default=0, help_text="Seconds")

    # Score
    earned_points = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_points = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    score_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_passed = models.BooleanField(default=False)

    # Grading
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_attempts')
    grading_notes = models.TextField(blank=True)

    # Proctoring
    proctoring_data = models.JSONField(default=dict, blank=True)
    flagged_for_review = models.BooleanField(default=False)

    # IP/Device tracking
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('assessment', 'student', 'attempt_number')
        ordering = ['-attempt_number']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['assessment', 'status']),
        ]

    def __str__(self):
        return f"{self.student.display_name} - {self.assessment.title} (Attempt {self.attempt_number})"

    def calculate_score(self):
        if self.total_points > 0:
            self.score_percentage = round((float(self.earned_points) / float(self.total_points)) * 100, 2)
            self.is_passed = self.score_percentage >= float(self.assessment.passing_score)
        self.save(update_fields=['score_percentage', 'is_passed'])


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuestionBank, on_delete=models.CASCADE)
    assessment_question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE)

    # Student response
    response = models.JSONField(default=dict, blank=True)
    response_text = models.TextField(blank=True)
    response_files = models.JSONField(default=list, blank=True)

    # Grading
    is_correct = models.BooleanField(null=True)
    points_earned = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_points = models.IntegerField(default=1)

    # Feedback
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_answers')
    graded_at = models.DateTimeField(null=True, blank=True)

    # Auto-grading metadata
    auto_graded = models.BooleanField(default=False)
    grading_details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('attempt', 'question')
        indexes = [
            models.Index(fields=['attempt', 'is_correct']),
        ]

    def __str__(self):
        return f"Answer to {self.question.title} - {self.points_earned}/{self.max_points}"


class Rubric(models.Model):
    assessment = models.OneToOneField(Assessment, on_delete=models.CASCADE, related_name='rubric')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    total_points = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Rubrics"

    def __str__(self):
        return f"Rubric: {self.name}"


class RubricCriterion(models.Model):
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name='criteria')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    points = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.name} ({self.points} pts)"


class RubricLevel(models.Model):
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name='levels')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    points = models.IntegerField(default=0)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.criterion.name} - {self.name}: {self.points} pts"


class RubricScore(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='rubric_scores')
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE)
    level = models.ForeignKey(RubricLevel, on_delete=models.CASCADE)
    points_earned = models.IntegerField(default=0)
    feedback = models.TextField(blank=True)

    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    graded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('attempt', 'criterion')

    def __str__(self):
        return f"{self.criterion.name}: {self.points_earned}/{self.level.points}"


class PeerReview(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = 'assigned', 'Assigned'
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUBMITTED = 'submitted', 'Submitted'
        REVIEWED = 'reviewed', 'Reviewed'

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='peer_reviews')
    submission = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='peer_reviews_received')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='peer_reviews_given')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ASSIGNED)
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    overall_feedback = models.TextField(blank=True)
    score_given = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rubric_scores = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('submission', 'reviewer')

    def __str__(self):
        return f"Review by {self.reviewer.display_name} for {self.submission.student.display_name}"