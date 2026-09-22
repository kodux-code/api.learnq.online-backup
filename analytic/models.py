from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class MetricType(models.TextChoices):
    COUNTER = 'counter', 'Counter'
    GAUGE = 'gauge', 'Gauge'
    HISTOGRAM = 'histogram', 'Histogram'
    RATE = 'rate', 'Rate'


class EventType(models.TextChoices):
    # User events
    USER_REGISTERED = 'user.registered', 'User Registered'
    USER_LOGIN = 'user.login', 'User Login'
    USER_LOGOUT = 'user.logout', 'User Logout'
    USER_VERIFIED = 'user.verified', 'User Verified'
    USER_DEACTIVATED = 'user.deactivated', 'User Deactivated'
    
    # Course events
    COURSE_CREATED = 'course.created', 'Course Created'
    COURSE_PUBLISHED = 'course.published', 'Course Published'
    COURSE_ENROLLED = 'course.enrolled', 'Course Enrolled'
    COURSE_COMPLETED = 'course.completed', 'Course Completed'
    COURSE_DROPPED = 'course.dropped', 'Course Dropped'
    LECTURE_COMPLETED = 'lecture.completed', 'Lecture Completed'
    
    # Assessment events
    ASSESSMENT_STARTED = 'assessment.started', 'Assessment Started'
    ASSESSMENT_SUBMITTED = 'assessment.submitted', 'Assessment Submitted'
    ASSESSMENT_GRADED = 'assessment.graded', 'Assessment Graded'
    ASSESSMENT_PASSED = 'assessment.passed', 'Assessment Passed'
    ASSESSMENT_FAILED = 'assessment.failed', 'Assessment Failed'
    
    # Payment events
    PAYMENT_INITIATED = 'payment.initiated', 'Payment Initiated'
    PAYMENT_COMPLETED = 'payment.completed', 'Payment Completed'
    PAYMENT_FAILED = 'payment.failed', 'Payment Failed'
    PAYMENT_REFUNDED = 'payment.refunded', 'Payment Refunded'
    SUBSCRIPTION_STARTED = 'subscription.started', 'Subscription Started'
    SUBSCRIPTION_CANCELLED = 'subscription.cancelled', 'Subscription Cancelled'
    SUBSCRIPTION_RENEWED = 'subscription.renewed', 'Subscription Renewed'
    
    # Earning events
    EARNING_ACCRUED = 'earning.accrued', 'Earning Accrued'
    PAYOUT_REQUESTED = 'payout.requested', 'Payout Requested'
    PAYOUT_COMPLETED = 'payout.completed', 'Payout Completed'
    
    # Engagement events
    MESSAGE_SENT = 'message.sent', 'Message Sent'
    THREAD_CREATED = 'thread.created', 'Thread Created'
    POST_CREATED = 'post.created', 'Post Created'
    COMMENT_CREATED = 'comment.created', 'Comment Created'
    LIKE_CREATED = 'like.created', 'Like Created'
    REVIEW_CREATED = 'review.created', 'Review Created'
    
    # Notification events
    NOTIFICATION_SENT = 'notification.sent', 'Notification Sent'
    NOTIFICATION_OPENED = 'notification.opened', 'Notification Opened'
    NOTIFICATION_CLICKED = 'notification.clicked', 'Notification Clicked'
    
    # System events
    ERROR_OCCURRED = 'error.occurred', 'Error Occurred'
    API_REQUEST = 'api.request', 'API Request'
    PAGE_VIEW = 'page.view', 'Page View'


class Event(models.Model):
    event_type = models.CharField(max_length=50, choices=EventType.choices, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='events', db_index=True)
    session_id = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Flexible properties
    properties = models.JSONField(default=dict, blank=True)
    
    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    referrer = models.URLField(blank=True)
    url = models.URLField(blank=True)
    
    # App/source tracking
    source_app = models.CharField(max_length=50, blank=True, db_index=True)
    source_version = models.CharField(max_length=20, blank=True)
    
    # Timestamps
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['user', 'event_type', 'timestamp']),
            models.Index(fields=['source_app', 'event_type', 'timestamp']),
        ]
        # partitioning = None  # Use with TimescaleDB or PostgreSQL partitioning
    
    def __str__(self):
        return f"{self.event_type} - {self.user.id or 'anonymous'} - {self.timestamp}"


class DailyMetric(models.Model):
    date = models.DateField(db_index=True)
    metric_name = models.CharField(max_length=100, db_index=True)
    metric_type = models.CharField(max_length=20, choices=MetricType.choices)
    
    # Dimensions for slicing
    app = models.CharField(max_length=50, blank=True, db_index=True)
    user_role = models.CharField(max_length=20, blank=True, db_index=True)
    country = models.CharField(max_length=2, blank=True, db_index=True)
    device_type = models.CharField(max_length=20, blank=True, db_index=True)
    dimension_key = models.CharField(max_length=100, blank=True, db_index=True)
    dimension_value = models.CharField(max_length=200, blank=True)
    
    # Values
    count = models.BigIntegerField(default=0)
    sum_value = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    min_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    avg_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    
    # Percentiles (stored as JSON)
    percentiles = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['date', 'metric_name', 'app', 'user_role', 'country', 'device_type', 'dimension_key', 'dimension_value']
        ordering = ['-date', 'metric_name']
        indexes = [
            models.Index(fields=['date', 'metric_name']),
            models.Index(fields=['app', 'date']),
        ]
    
    def __str__(self):
        return f"{self.metric_name} ({self.date}) - {self.count}"


class HourlyMetric(models.Model):
    """Hourly rollup for real-time dashboards."""
    hour = models.DateTimeField(db_index=True)
    metric_name = models.CharField(max_length=100, db_index=True)
    app = models.CharField(max_length=50, blank=True, db_index=True)
    count = models.BigIntegerField(default=0)
    sum_value = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['hour', 'metric_name', 'app']
        ordering = ['-hour']
        indexes = [
            models.Index(fields=['hour', 'metric_name']),
        ]


class Dashboard(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboards')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)
    layout = models.JSONField(default=dict, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.name


class DashboardWidget(models.Model):
    class WidgetType(models.TextChoices):
        LINE_CHART = 'line_chart', 'Line Chart'
        BAR_CHART = 'bar_chart', 'Bar Chart'
        PIE_CHART = 'pie_chart', 'Pie Chart'
        METRIC_CARD = 'metric_card', 'Metric Card'
        TABLE = 'table', 'Table'
        FUNNEL = 'funnel', 'Funnel'
        RETENTION = 'retention', 'Retention Heatmap'
        COHORT = 'cohort', 'Cohort Analysis'
        GEO_MAP = 'geo_map', 'Geo Map'
    
    class TimeGranularity(models.TextChoices):
        MINUTE = 'minute', 'Minute'
        HOUR = 'hour', 'Hour'
        DAY = 'day', 'Day'
        WEEK = 'week', 'Week'
        MONTH = 'month', 'Month'
    
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name='widgets')
    widget_type = models.CharField(max_length=20, choices=WidgetType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Query configuration
    metric_names = models.JSONField(default=list)  # List of metric names
    dimensions = models.JSONField(default=dict, blank=True)  # Group by dimensions
    filters = models.JSONField(default=dict, blank=True)
    time_range = models.JSONField(default=dict)  # {preset: 'last_7_days', custom: {start, end}}
    granularity = models.CharField(max_length=10, choices=TimeGranularity.choices, default=TimeGranularity.DAY)
    
    # Visualization options
    chart_options = models.JSONField(default=dict, blank=True)
    colors = models.JSONField(default=list, blank=True)
    
    # Layout
    x = models.IntegerField(default=0)
    y = models.IntegerField(default=0)
    width = models.IntegerField(default=6)
    height = models.IntegerField(default=4)
    
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['y', 'x']
    
    def __str__(self):
        return f"{self.dashboard.name} - {self.title}"


class Report(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        GENERATING = 'generating', 'Generating'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
    
    class Format(models.TextChoices):
        JSON = 'json', 'JSON'
        CSV = 'csv', 'CSV'
        PDF = 'pdf', 'PDF'
        EXCEL = 'excel', 'Excel'
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    format = models.CharField(max_length=10, choices=Format.choices, default=Format.JSON)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Query definition
    query = models.JSONField(default=dict)
    
    # Schedule
    is_scheduled = models.BooleanField(default=False)
    schedule_cron = models.CharField(max_length=100, blank=True)
    schedule_timezone = models.CharField(max_length=50, default='UTC')
    last_generated_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    
    # Output
    file = models.FileField(upload_to='analytics/reports/', null=True, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    row_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class RetentionCohort(models.Model):
    """Pre-computed retention cohorts for fast queries."""
    cohort_date = models.DateField(db_index=True)
    cohort_size = models.IntegerField(default=0)
    period = models.IntegerField(default=0)  # 0 = cohort day, 1 = day 1, 7 = day 7, etc.
    period_type = models.CharField(max_length=10, choices=[('day', 'Day'), ('week', 'Week'), ('month', 'Month')])
    retained_users = models.IntegerField(default=0)
    retention_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Dimensions
    app = models.CharField(max_length=50, blank=True, db_index=True)
    user_role = models.CharField(max_length=20, blank=True, db_index=True)
    acquisition_channel = models.CharField(max_length=50, blank=True, db_index=True)
    
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['cohort_date', 'period', 'period_type', 'app', 'user_role', 'acquisition_channel']
        ordering = ['-cohort_date', 'period']
        indexes = [
            models.Index(fields=['cohort_date', 'period_type']),
        ]


class FunnelStep(models.Model):
    funnel_name = models.CharField(max_length=100, db_index=True)
    step_order = models.IntegerField()
    step_name = models.CharField(max_length=100)
    event_type = models.CharField(max_length=50)
    filters = models.JSONField(default=dict, blank=True)
    
    class Meta:
        unique_together = ['funnel_name', 'step_order']
        ordering = ['funnel_name', 'step_order']


class Alert(models.Model):
    class Severity(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        CRITICAL = 'critical', 'Critical'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
        RESOLVED = 'resolved', 'Resolved'
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    metric_name = models.CharField(max_length=100)
    condition = models.JSONField(default=dict)  # {operator: 'gt', threshold: 100, window: '5m'}
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    # Notification
    notify_channels = models.JSONField(default=list)  # ['email', 'slack', 'webhook']
    notify_users = models.ManyToManyField(User, blank=True, related_name='alerts')
    cooldown_minutes = models.IntegerField(default=60)
    
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    trigger_count = models.IntegerField(default=0)
    
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.severity})"


class AlertTrigger(models.Model):
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='triggers')
    triggered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metric_value = models.DecimalField(max_digits=20, decimal_places=4)
    threshold_value = models.DecimalField(max_digits=20, decimal_places=4)
    context = models.JSONField(default=dict, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='acknowledged_alerts')
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-triggered_at']
        indexes = [
            models.Index(fields=['alert', 'triggered_at']),
        ]


class AnalyticsSettings(models.Model):
    """Global analytics configuration."""
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict)
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Analytics Settings"
    
    def __str__(self):
        return self.key