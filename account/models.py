from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

User = settings.AUTH_USER_MODEL


class StudentAccount(models.Model):
    client = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='student_account',
        primary_key=True
    )
    grade_level = models.CharField(max_length=20, blank=True)
    parent_email = models.EmailField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    gpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(4)])
    credits_earned = models.IntegerField(default=0)

    notification_email = models.BooleanField(default=True)
    notification_push = models.BooleanField(default=True)
    preferred_language = models.CharField(max_length=10, default='en')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Account"
        verbose_name_plural = "Student Accounts"
        indexes = [
            models.Index(fields=['grade_level']),
        ]

    def __str__(self):
        return f"Student: {self.client.display_name}"


class TeacherAccount(models.Model):
    client = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='teacher_account',
        primary_key=True
    )
    bio = models.TextField(blank=True)
    qualifications = models.TextField(blank=True)

    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='USD')
    stripe_account_id = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)

    total_students = models.IntegerField(default=0)
    total_courses = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    review_count = models.IntegerField(default=0)

    auto_payout = models.BooleanField(default=False)
    payout_schedule = models.CharField(
        max_length=20,
        choices=[('weekly', 'Weekly'), ('monthly', 'Monthly'), ('manual', 'Manual')],
        default='monthly'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Teacher Account"
        verbose_name_plural = "Teacher Accounts"
        indexes = [
            models.Index(fields=['rating']),
            models.Index(fields=['stripe_account_id']),
        ]

    def __str__(self):
        return f"Teacher: {self.client.display_name}"


class ModeratorAccount(models.Model):
    client = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='moderator_account',
        primary_key=True
    )
    permissions = models.JSONField(default=dict)
    department = models.CharField(max_length=50, blank=True)
    is_senior = models.BooleanField(default=False)

    actions_taken = models.IntegerField(default=0)
    last_action_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Moderator Account"
        verbose_name_plural = "Moderator Accounts"
        indexes = [
            models.Index(fields=['department']),
            models.Index(fields=['is_senior']),
        ]

    def __str__(self):
        return f"Moderator: {self.client.display_name}"