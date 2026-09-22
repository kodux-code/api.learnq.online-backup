import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Sum
from django.utils import timezone
from django.conf import settings

from client.models import Client


class QuestionTag(models.Model):
    """Tags for categorizing questions."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6366f1')
    description = models.TextField(blank=True)
    question_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_open = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Tags for categorization
    tags = models.ManyToManyField(QuestionTag, related_name="questions", blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["-is_pinned", "-created_at"]),
            models.Index(fields=["author", "-created_at"]),
            models.Index(fields=["is_open", "-created_at"]),
            models.Index(fields=["is_deleted", "created_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def vote_score(self) -> int:
        return self.votes.aggregate(score=Sum("value"))["score"] or 0

    @property
    def answer_count(self) -> int:
        return self.answers.filter(is_deleted=False).count()

    @property
    def share_count(self) -> int:
        return self.shares.count()

    def close(self):
        self.is_open = False
        self.closed_at = timezone.now()
        self.save(update_fields=['is_open', 'closed_at', 'updated_at'])

    def reopen(self):
        self.is_open = True
        self.closed_at = None
        self.save(update_fields=['is_open', 'closed_at', 'updated_at'])

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])


class Answer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    body = models.TextField()
    is_accepted = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_accepted", "created_at"]
        indexes = [
            models.Index(fields=["question", "-is_accepted", "created_at"]),
            models.Index(fields=["parent", "created_at"]),
            models.Index(fields=["author", "created_at"]),
        ]

    def __str__(self):
        return f"Answer by {self.author.email} on {self.question.title}"

    def clean(self):
        super().clean()

        if not self.parent_id:
            return

        if self.parent.question_id != self.question_id:
            raise ValidationError(
                {"parent": "A reply must belong to the same question as its parent."}
            )

        ancestor = self.parent
        while ancestor:
            if ancestor.pk == self.pk:
                raise ValidationError(
                    {"parent": "An answer cannot be a parent of itself."}
                )
            ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def accept(self):
        # Unaccept other answers for this question
        Answer.objects.filter(question=self.question, is_accepted=True).update(
            is_accepted=False
        )
        self.is_accepted = True
        self.save(update_fields=['is_accepted', 'updated_at'])
        
        # Close the question
        self.question.close()

    def unaccept(self):
        self.is_accepted = False
        self.save(update_fields=['is_accepted', 'updated_at'])

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    @property
    def vote_score(self) -> int:
        return self.votes.aggregate(score=Sum("value"))["score"] or 0

    @property
    def reply_count(self) -> int:
        return self.replies.filter(is_deleted=False).count()


class Vote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Value(models.IntegerChoices):
        DOWN = -1, "Downvote"
        UP = 1, "Upvote"

    voter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="votes",
    )
    answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="votes",
    )
    value = models.SmallIntegerField(choices=Value.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(question__isnull=False, answer__isnull=True)
                    | models.Q(question__isnull=True, answer__isnull=False)
                ),
                name="vote_must_target_exactly_one_object",
            ),
            models.UniqueConstraint(
                fields=["voter", "question"],
                condition=models.Q(question__isnull=False),
                name="one_question_vote_per_user",
            ),
            models.UniqueConstraint(
                fields=["voter", "answer"],
                condition=models.Q(answer__isnull=False),
                name="one_answer_vote_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["question"]),
            models.Index(fields=["answer"]),
            models.Index(fields=["voter", "created_at"]),
        ]

    def __str__(self):
        target = self.question or self.answer
        return f"{self.get_value_display()} by {self.voter.email} on {target}"

    def save(self, *args, **kwargs):
        # Determine target for signal
        self.full_clean()
        super().save(*args, **kwargs)


class QuestionShare(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Channel(models.TextChoices):
        LINK = "link", "Copy link"
        WHATSAPP = "whatsapp", "WhatsApp"
        FACEBOOK = "facebook", "Facebook"
        X = "x", "X"
        EMAIL = "email", "Email"

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="shares",
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="question_shares",
    )
    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        default=Channel.LINK,
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["question", "-created_at"]),
            models.Index(fields=["shared_by", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.question.title} shared by {self.shared_by.email}"


class AnswerReport(models.Model):
    """Reports for inappropriate answers."""
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment"
        INAPPROPRIATE = "inappropriate", "Inappropriate Content"
        MISINFORMATION = "misinformation", "Misinformation"
        PLAGIARISM = "plagiarism", "Plagiarism"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="answer_reports"
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    details = models.TextField(blank=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_answer_reports"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["answer", "-created_at"]),
            models.Index(fields=["is_resolved", "created_at"]),
        ]