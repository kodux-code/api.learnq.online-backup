import uuid
from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from django.core.validators import EmailValidator


class ClientManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email address is required.")

        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', False)
        extra_fields.setdefault('role', 'student')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'moderator')
        return self.create_user(email, password, **extra_fields)

    def get_by_email(self, email):
        return self.get_queryset().get(email__iexact=email)


class Client(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        TEACHER = 'teacher', 'Teacher'
        MODERATOR = 'moderator', 'Moderator'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    email = models.EmailField(
        unique=True,
        max_length=255,
        validators=[EmailValidator()],
        error_messages={
            'unique': "An account with that email address already exists."
        }
    )

    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    display_name = models.CharField(max_length=50, unique=True)
    bio = models.TextField(blank=True, default='')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        db_index=True
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Inactive accounts cannot log in"
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Email verification status"
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Django admin access"
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClientManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'display_name', 'role']

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['role', 'is_active']),
            models.Index(fields=['is_verified', 'created_at']),
            models.Index(fields=['display_name']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.email})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_moderator(self):
        return self.role == self.Role.MODERATOR or self.is_staff

    def get_account(self):
        """Get the role-specific account profile."""
        if self.is_student:
            return getattr(self, 'student_account', None)
        elif self.is_teacher:
            return getattr(self, 'teacher_account', None)
        elif self.is_moderator:
            return getattr(self, 'moderator_account', None)
        return None


class ClientFollow(models.Model):
    follower = models.ForeignKey(
        Client,
        related_name='following_relationships',
        on_delete=models.CASCADE,
    )
    following = models.ForeignKey(
        Client,
        related_name='follower_relationships',
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('follower', 'following')
        verbose_name = "Client Follow"
        verbose_name_plural = "Client Follows"
        indexes = [
            models.Index(fields=['follower', 'created_at']),
            models.Index(fields=['following', 'created_at']),
        ]

    def __str__(self):
        return f"{self.follower.display_name} follows {self.following.display_name}"

    def clean(self):
        if self.follower == self.following:
            raise ValueError("A user cannot follow themselves")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)