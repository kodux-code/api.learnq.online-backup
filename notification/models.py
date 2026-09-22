from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator, MaxValueValidator

User = settings.AUTH_USER_MODEL


class NotificationChannel(models.TextChoices):
    IN_APP = 'in_app', 'In-App'
    EMAIL = 'email', 'Email'
    PUSH = 'push', 'Push'
    SMS = 'sms', 'SMS'
    WEBHOOK = 'webhook', 'Webhook'


class NotificationPriority(models.TextChoices):
    LOW = 'low', 'Low'
    NORMAL = 'normal', 'Normal'
    HIGH = 'high', 'High'
    URGENT = 'urgent', 'Urgent'


class NotificationTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    # Channel-specific templates
    subject_template = models.CharField(max_length=200, blank=True)
    body_template = models.TextField()
    html_template = models.TextField(blank=True)
    push_title_template = models.CharField(max_length=200, blank=True)
    push_body_template = models.CharField(max_length=300, blank=True)

    # Variables
    available_variables = models.JSONField(default=list, blank=True)
    required_variables = models.JSONField(default=list, blank=True)

    # Channels this template supports
    channels = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class NotificationPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preferences', primary_key=True)

    # Global toggles
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    sms_enabled = models.BooleanField(default=False)

    # Per-category preferences (JSON)
    category_preferences = models.JSONField(default=dict, blank=True)

    # Quiet hours
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')

    # Frequency
    digest_frequency = models.CharField(
        max_length=20,
        choices=[('realtime', 'Real-time'), ('hourly', 'Hourly'), ('daily', 'Daily'), ('weekly', 'Weekly'), ('never', 'Never')],
        default='realtime'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"

    def __str__(self):
        return f"Preferences for {self.user.display_name}"

    def is_channel_enabled(self, channel, category=None):
        if not getattr(self, f'{channel}_enabled', False):
            return False

        if category and self.category_preferences:
            cat_pref = self.category_preferences.get(category, {})
            if cat_pref.get(channel) is False:
                return False

        return True


class Notification(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        FAILED = 'failed', 'Failed'
        READ = 'read', 'Read'
        ARCHIVED = 'archived', 'Archived'

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')

    # Template reference
    template = models.ForeignKey(NotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')

    # Content
    title = models.CharField(max_length=255)
    message = models.TextField()
    html_message = models.TextField(blank=True)

    # Categorization
    category = models.CharField(max_length=50, db_index=True)
    action_url = models.CharField(max_length=500, blank=True)
    action_text = models.CharField(max_length=100, blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, blank=True)

    # Priority & channels
    priority = models.CharField(max_length=10, choices=NotificationPriority.choices, default=NotificationPriority.NORMAL)
    channels = models.JSONField(default=list, blank=True)

    # Generic relation for related object
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Status tracking
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['recipient', 'category']),
            models.Index(fields=['recipient', 'created_at']),
            models.Index(fields=['template', 'status']),
        ]

    def __str__(self):
        return f"{self.title} -> {self.recipient.display_name}"

    def mark_read(self):
        if self.status != self.Status.READ:
            self.status = self.Status.READ
            self.read_at = timezone.now()
            self.save(update_fields=['status', 'read_at', 'updated_at'])

    def mark_archived(self):
        self.status = self.Status.ARCHIVED
        self.archived_at = timezone.now()
        self.save(update_fields=['status', 'archived_at', 'updated_at'])


class NotificationBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partial'

    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE, related_name='batches')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Recipient selection
    recipient_filter = models.JSONField(default=dict, blank=True)
    recipient_count = models.IntegerField(default=0)

    # Scheduling
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Results
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)

    # Channels to send
    channels = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_notification_batches')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Batch: {self.name} ({self.status})"


class DeviceToken(models.Model):
    class Platform(models.TextChoices):
        IOS = 'ios', 'iOS'
        ANDROID = 'android', 'Android'
        WEB = 'web', 'Web'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=500)
    platform = models.CharField(max_length=10, choices=Platform.choices)
    device_id = models.CharField(max_length=200, blank=True)
    device_name = models.CharField(max_length=200, blank=True)
    app_version = models.CharField(max_length=50, blank=True)
    os_version = models.CharField(max_length=50, blank=True)

    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'token')
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.display_name} - {self.platform}"


class PushNotificationLog(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='push_logs')
    device_token = models.ForeignKey(DeviceToken, on_delete=models.CASCADE, related_name='push_logs')

    class Status(models.TextChoices):
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        FAILED = 'failed', 'Failed'
        CLICKED = 'clicked', 'Clicked'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
    provider = models.CharField(max_length=50, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error_message = models.TextField(blank=True)

    sent_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Push: {self.notification.title} -> {self.device_token.user.display_name} ({self.status})"


class EmailNotificationLog(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='email_logs')

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        BOUNCED = 'bounced', 'Bounced'
        FAILED = 'failed', 'Failed'
        OPENED = 'opened', 'Opened'
        CLICKED = 'clicked', 'Clicked'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    provider = models.CharField(max_length=50, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error_message = models.TextField(blank=True)

    recipient_email = models.EmailField()
    subject = models.CharField(max_length=200)

    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Email: {self.subject} -> {self.recipient_email} ({self.status})"


class InAppNotificationGroup(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_groups')
    category = models.CharField(max_length=50)
    count = models.IntegerField(default=0)
    last_notification = models.ForeignKey(Notification, on_delete=models.SET_NULL, null=True, blank=True)
    is_expanded = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'category')

    def __str__(self):
        return f"{self.user.display_name} - {self.category}: {self.count}"


from django.utils import timezone