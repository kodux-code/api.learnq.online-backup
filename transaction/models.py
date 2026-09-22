import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class TransactionDirection(models.TextChoices):
    INCOMING = 'incoming', 'Incoming (Revenue)'
    OUTGOING = 'outgoing', 'Outgoing (Payout/Expense)'


class TransactionType(models.TextChoices):
    # Incoming
    COURSE_SALE = 'course_sale', 'Course Sale'
    SUBSCRIPTION = 'subscription', 'Subscription'
    BUNDLE_SALE = 'bundle_sale', 'Bundle Sale'
    UPGRADE = 'upgrade', 'Upgrade'
    DONATION = 'donation', 'Donation'
    REFUND_RECEIVED = 'refund_received', 'Refund Received'
    
    # Outgoing
    TEACHER_PAYOUT = 'teacher_payout', 'Teacher Payout'
    PLATFORM_FEE = 'platform_fee', 'Platform Fee'
    REFUND_ISSUED = 'refund_issued', 'Refund Issued'
    ADJUSTMENT = 'adjustment', 'Adjustment'
    BONUS = 'bonus', 'Bonus'
    WITHDRAWAL = 'withdrawal', 'Withdrawal'
    TRANSFER = 'transfer', 'Transfer'


class TransactionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    REVERSED = 'reversed', 'Reversed'
    REFUNDED = 'refunded', 'Refunded'
    CANCELLED = 'cancelled', 'Cancelled'


class Transaction(models.Model):
    """
    Unified transaction model for all financial movements.
    Direction: 'incoming' = money coming in (revenue), 'outgoing' = money going out (payouts/expenses)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core references
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions', db_index=True)
    # For incoming: user is the buyer (student)
    # For outgoing: user is the recipient (teacher)
    
    # Direction and type
    direction = models.CharField(max_length=10, choices=TransactionDirection.choices, db_index=True)
    transaction_type = models.CharField(max_length=30, choices=TransactionType.choices, db_index=True)
    status = models.CharField(max_length=20, choices=TransactionStatus.choices, default=TransactionStatus.PENDING, db_index=True)
    
    # Amounts
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='USD')
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    
    # Counterparty (for incoming: student; for outgoing: teacher)
    counterparty = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='counterparty_transactions', db_index=True)
    
    # Related objects
    course = models.ForeignKey('course.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', db_index=True)
    enrollment = models.ForeignKey('course.Enrollment', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    assessment = models.ForeignKey('assessment.Attempt', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    order = models.ForeignKey('payment.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='unified_transactions')
    subscription = models.ForeignKey('payment.Subscription', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    bundle = models.ForeignKey('payment.Bundle', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    
    # Gateway info
    gateway = models.CharField(max_length=20, choices=[
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('razorpay', 'Razorpay'),
        ('manual', 'Manual'),
        ('internal', 'Internal'),
    ], blank=True)
    gateway_transaction_id = models.CharField(max_length=200, blank=True, db_index=True)
    gateway_transfer_id = models.CharField(max_length=200, blank=True)
    gateway_payout_id = models.CharField(max_length=200, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Revenue sharing (for course sales)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='teacher_transactions')
    revenue_share_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    teacher_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Payout info
    payout = models.ForeignKey('earning.Payout', on_delete=models.SET_NULL, null=True, blank=True, related_name='unified_transactions')
    payout_method = models.CharField(max_length=20, choices=[
        ('stripe', 'Stripe'),
        ('bank_transfer', 'Bank Transfer'),
        ('paypal', 'PayPal'),
        ('wise', 'Wise'),
    ], blank=True)
    
    # Metadata
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Billing info (for incoming)
    billing_email = models.EmailField(blank=True)
    billing_name = models.CharField(max_length=200, blank=True)
    billing_address = models.JSONField(default=dict, blank=True)
    billing_country = models.CharField(max_length=2, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Coupon
    coupon = models.ForeignKey('payment.Coupon', on_delete=models.SET_NULL, null=True, blank=True, related_name='unified_transactions')
    coupon_code = models.CharField(max_length=50, blank=True)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Timestamps
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'direction', 'status']),
            models.Index(fields=['teacher', 'direction', 'status']),
            models.Index(fields=['course', 'direction']),
            models.Index(fields=['transaction_type', 'status']),
            models.Index(fields=['gateway_transaction_id']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.direction} - {self.transaction_type} - ${self.amount} ({self.status})"
    
    def save(self, *args, **kwargs):
        # Auto-set direction based on transaction_type
        if not self.direction:
            incoming_types = [
                TransactionType.COURSE_SALE, TransactionType.SUBSCRIPTION,
                TransactionType.BUNDLE_SALE, TransactionType.UPGRADE,
                TransactionType.DONATION, TransactionType.REFUND_RECEIVED
            ]
            if self.transaction_type in incoming_types:
                self.direction = TransactionDirection.INCOMING
            else:
                self.direction = TransactionDirection.OUTGOING
        
        # Auto-set net_amount if not provided
        if not self.net_amount:
            self.net_amount = self.amount - self.platform_fee
        
        super().save(*args, **kwargs)
    
    def mark_completed(self):
        self.status = TransactionStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        
        # Update teacher earnings if this is a course sale
        if self.direction == TransactionDirection.INCOMING and self.transaction_type == TransactionType.COURSE_SALE:
            self._update_teacher_earnings()
    
    def _update_teacher_earnings(self):
        if self.teacher:
            from earning.models import TeacherEarning
            earning, _ = TeacherEarning.objects.get_or_create(teacher=self.teacher)
            earning.add_earning(self.teacher_amount or self.net_amount)
            
            # Link this transaction to the earning
            self.earning = earning
            self.save(update_fields=['earning', 'updated_at'])
    
    def mark_failed(self, reason=''):
        self.status = TransactionStatus.FAILED
        self.failed_at = timezone.now()
        if reason:
            self.metadata['failure_reason'] = reason
        self.save(update_fields=['status', 'failed_at', 'metadata', 'updated_at'])
    
    def mark_reversed(self):
        self.status = TransactionStatus.REVERSED
        self.save(update_fields=['status', 'updated_at'])
    
    def mark_refunded(self):
        self.status = TransactionStatus.REFUNDED
        self.save(update_fields=['status', 'updated_at'])


class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet', primary_key=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"
    
    def __str__(self):
        return f"Wallet: {self.user.display_name} - {self.balance} {self.currency}"
    
    def add_funds(self, amount, description='', reference_id='', reference_type=''):
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])
        WalletTransaction.objects.create(
            wallet=self,
            type=WalletTransaction.Type.TOP_UP,
            amount=amount,
            balance_before=self.balance - amount,
            balance_after=self.balance,
            description=description,
            reference_id=reference_id,
            reference_type=reference_type
        )
    
    def deduct_funds(self, amount, description='', reference_id='', reference_type=''):
        if self.balance < amount:
            raise ValueError("Insufficient funds")
        self.balance -= amount
        self.save(update_fields=['balance', 'updated_at'])
        WalletTransaction.objects.create(
            wallet=self,
            type=WalletTransaction.Type.WITHDRAWAL,
            amount=amount,
            balance_before=self.balance + amount,
            balance_after=self.balance,
            description=description,
            reference_id=reference_id,
            reference_type=reference_type
        )


class WalletTransaction(models.Model):
    class Type(models.TextChoices):
        TOP_UP = 'top_up', 'Top Up'
        PURCHASE = 'purchase', 'Purchase'
        REFUND = 'refund', 'Refund'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        BONUS = 'bonus', 'Bonus'
        TRANSFER_IN = 'transfer_in', 'Transfer In'
        TRANSFER_OUT = 'transfer_out', 'Transfer Out'
    
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='wallet_transactions')
    type = models.CharField(max_length=20, choices=Type.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_before = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    reference_id = models.CharField(max_length=100, blank=True)
    reference_type = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.type}: {self.amount} ({self.wallet.user.display_name})"