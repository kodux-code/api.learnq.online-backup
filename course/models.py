
import uuid

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from client.models import Client


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Course(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING_REVIEW = 'pending_review', 'Pending Review'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'
        REJECTED = 'rejected', 'Rejected'

    class Level(models.TextChoices):
        BEGINNER = 'beginner', 'Beginner'
        INTERMEDIATE = 'intermediate', 'Intermediate'
        ADVANCED = 'advanced', 'Advanced'
        ALL = 'all', 'All Levels'
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    subtitle = models.CharField(max_length=300, blank=True)
    description = models.TextField()

    thumbnail = models.ImageField(upload_to='course_thumbnails/', null=True, blank=True)
    preview_video = models.URLField(blank=True)

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='courses')
    subcategory = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategory_courses')

    level = models.CharField(max_length=20, choices=Level.choices, default=Level.ALL)
    language = models.CharField(max_length=10, default='en')
    caption_languages = models.JSONField(default=list, blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    is_free = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)

    meta_title = models.CharField(max_length=60, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    total_students = models.IntegerField(default=0)
    total_reviews = models.IntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_duration_minutes = models.IntegerField(default=0)
    total_lectures = models.IntegerField(default=0)

    requirements = models.JSONField(default=list, blank=True)
    learning_outcomes = models.JSONField(default=list, blank=True)
    target_audience = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'category']),
            models.Index(fields=['status', 'is_free']),
            models.Index(fields=['average_rating', 'total_students']),
        ]

    def __str__(self):
        return self.title

    @property
    def current_price(self):
        if self.is_free:
            return 0
        return self.sale_price if self.sale_price else self.price

    @property
    def discount_percentage(self):
        if self.price and self.sale_price and self.sale_price < self.price:
            return round((1 - float(self.sale_price) / float(self.price)) * 100)
        return 0


class CourseTeacher(models.Model):
    class Role(models.TextChoices):
        PRIMARY = 'primary', 'Primary Instructor'
        CO_INSTRUCTOR = 'co_instructor', 'Co-Instructor'
        ASSISTANT = 'assistant', 'Teaching Assistant'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='course_teachers')
    teacher = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='teacher_courses')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CO_INSTRUCTOR)
    revenue_share = models.DecimalField(max_digits=5, decimal_places=2, default=100.00, validators=[MinValueValidator(0), MaxValueValidator(100)])

    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('course', 'teacher')
        verbose_name = "Course Teacher"
        verbose_name_plural = "Course Teachers"

    def __str__(self):
        return f"{self.teacher.display_name} - {self.course.title} ({self.role})"


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    is_free_preview = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        unique_together = ('course', 'order')

    def __str__(self):
        return f"{self.course.title} - Section {self.order}: {self.title}"


class Lecture(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Type(models.TextChoices):
        VIDEO = 'video', 'Video'
        ARTICLE = 'article', 'Article'
        QUIZ = 'quiz', 'Quiz'
        ASSIGNMENT = 'assignment', 'Assignment'
        LIVE = 'live', 'Live Session'
        DOWNLOAD = 'download', 'Downloadable Resource'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        HIDDEN = 'hidden', 'Hidden'

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='lectures')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.VIDEO)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    video_url = models.URLField(blank=True)
    video_duration = models.IntegerField(default=0)
    video_provider = models.CharField(max_length=20, choices=[('youtube', 'YouTube'), ('vimeo', 'Vimeo'), ('self_hosted', 'Self Hosted')], blank=True)

    content = models.TextField(blank=True)

    passing_score = models.IntegerField(default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])
    max_attempts = models.IntegerField(default=0)

    order = models.IntegerField(default=0)
    is_free_preview = models.BooleanField(default=False)
    is_downloadable = models.BooleanField(default=False)
    resources = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        unique_together = ('section', 'order')

    def __str__(self):
        return f"{self.section.course.title} - {self.title}"


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        DROPPED = 'dropped', 'Dropped'
        REFUNDED = 'refunded', 'Refunded'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    last_accessed_lecture = models.ForeignKey(Lecture, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    completed_lectures = models.ManyToManyField(Lecture, related_name='completed_by', blank=True)

    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    payment_id = models.CharField(max_length=100, blank=True)
    enrolled_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    certificate_issued = models.BooleanField(default=False)
    certificate_id = models.CharField(max_length=100, blank=True)
    certificate_issued_at = models.DateTimeField(null=True, blank=True)

    has_reviewed = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'course')
        ordering = ['-enrolled_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['course', 'status']),
        ]

    def __str__(self):
        return f"{self.student.display_name} enrolled in {self.course.title}"


class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='review')
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=200, blank=True)
    content = models.TextField()

    content_quality = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    instructor_skill = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    course_value = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])

    is_verified = models.BooleanField(default=True)
    helpful_count = models.IntegerField(default=0)
    instructor_response = models.TextField(blank=True)
    instructor_responded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.enrollment.student.display_name} - {self.rating}★ - {self.enrollment.course.title}"


class Announcement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='announcements')
    teacher = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='course_announcements')
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_published = models.BooleanField(default=True)
    send_email = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Announcement: {self.title} ({self.course.title})"


class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='questions', null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='questions')
    student = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='questions_asked')

    title = models.CharField(max_length=200)
    content = models.TextField()
    is_answered = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)

    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"Q: {self.title} ({self.course.title})"


class Answer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    teacher = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='answers_given')
    content = models.TextField()
    is_accepted = models.BooleanField(default=False)

    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_accepted', '-created_at']

    def __str__(self):
        return f"Answer to {self.question.title} by {self.teacher.display_name}"


class LectureProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='lecture_progress')
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='progress_records')

    watch_time = models.IntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_position = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('enrollment', 'lecture')

    def __str__(self):
        status = "✓" if self.is_completed else "○"
        return f"{status} {self.lecture.title} - {self.enrollment.student.display_name}"


class CourseAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='attachments')
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='attachments', null=True, blank=True)

    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='course_attachments/')
    file_size = models.IntegerField(default=0)
    file_type = models.CharField(max_length=50, blank=True)
    is_downloadable = models.BooleanField(default=True)

    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.title} ({self.course.title})"