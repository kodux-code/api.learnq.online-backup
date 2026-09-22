from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class TeacherEarning(models.Model):
    teacher = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='earning_profile',
        primary_key=True
    )

    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    pending_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    available_for_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    lifetime_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    last_payout_at = models.DateTimeField(null=True, blank=True)
    last_payout_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    currency = models.CharField(max_length=3, default='USD')
    stripe_account_id = models.CharField(max_length=100, blank=True)
    stripe_onboarding_complete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Teacher Earning"
        verbose_name_plural = "Teacher Earnings"
        indexes = [
            models.Index(fields=['pending_payout']),
            models.Index(fields=['stripe_onboarding_complete']),
        ]

    def __str__(self):
        return f"Earnings for {self.teacher.display_name}: ${self.total_earned}"

    def add_earning(self, amount, transaction_type='course_sale'):
        self.total_earned += amount
        self.pending_payout += amount
        self.available_for_payout += amount
        self.save(update_fields=['total_earned', 'pending_payout', 'available_for_payout', 'updated_at'])

    def record_payout(self, amount):
        self.pending_payout -= amount
        self.available_for_payout -= amount
        self.lifetime_payout += amount
        self.last_payout_at = timezone.now()
        self.last_payout_amount = amount
        self.save(update_fields=['pending_payout', 'available_for_payout', 'lifetime_payout', 'last_payout_at', 'last_payout_amount', 'updated_at'])


class Payout(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    class Method(models.TextChoices):
        STRIPE = 'stripe', 'Stripe'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        PAYPAL = 'paypal', 'PayPal'
        WISE = 'wise', 'Wise'

    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts')
    earning = models.ForeignKey(TeacherEarning, on_delete=models.CASCADE, related_name='payouts')

    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='USD')
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.STRIPE)

    stripe_payout_id = models.CharField(max_length=100, blank=True, db_index=True)
    bank_transfer_id = models.CharField(max_length=100, blank=True)

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Use unified transaction.Transaction instead of local Transaction
    transactions = models.ManyToManyField('transaction.Transaction', related_name='earning_payouts', blank=True)

    failure_reason = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)

    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['teacher', 'status']),
            models.Index(fields=['status', 'requested_at']),
        ]

    def __str__(self):
        return f"Payout ${self.amount} for {self.teacher.display_name} ({self.status})"

    def mark_processing(self):
        self.status = self.Status.PROCESSING
        self.save(update_fields=['status', 'updated_at'])

    def mark_paid(self):
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'paid_at', 'updated_at'])
        self.earning.record_payout(self.amount)

    def mark_failed(self, reason):
        self.status = self.Status.FAILED
        self.failure_reason = reason
        self.save(update_fields=['status', 'failure_reason', 'updated_at'])


class PayoutSchedule(models.Model):
    teacher = models.OneToOneField(User, on_delete=models.CASCADE, related_name='payout_schedule', primary_key=True)

    schedule = models.CharField(
        max_length=20,
        choices=[('daily', 'Daily'), ('weekly', 'Weekly'), ('biweekly', 'Bi-weekly'), ('monthly', 'Monthly'), ('manual', 'Manual')],
        default='monthly'
    )
    day_of_week = models.IntegerField(choices=[(i, d) for i, d in enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])], null=True, blank=True)
    day_of_month = models.IntegerField(null=True, blank=True)
    minimum_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, validators=[MinValueValidator(0)])

    auto_payout = models.BooleanField(default=False)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)

    timezone = models.CharField(max_length=50, default='UTC')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payout Schedule"
        verbose_name_plural = "Payout Schedules"

    def __str__(self):
        return f"Payout Schedule for {self.teacher.display_name}: {self.schedule}"


class RevenueReport(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='revenue_reports')
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    gross_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    platform_fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refunds = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payouts = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    courses_count = models.IntegerField(default=0)
    sales_count = models.IntegerField(default=0)
    students_count = models.IntegerField(default=0)

    report_data = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('teacher', 'period_start', 'period_end')
        ordering = ['-period_start']
        indexes = [
            models.Index(fields=['teacher', 'period_start']),
        ]

    def __str__(self):
        return f"Revenue Report for {self.teacher.display_name} ({self.period_start.date()} - {self.period_end.date()})"