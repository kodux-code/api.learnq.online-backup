from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class PaymentGateway(models.TextChoices):
    STRIPE = 'stripe', 'Stripe'
    PAYPAL = 'paypal', 'PayPal'
    RAZORPAY = 'razorpay', 'Razorpay'
    MANUAL = 'manual', 'Manual'


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED = 'fixed', 'Fixed Amount'

    class Scope(models.TextChoices):
        GLOBAL = 'global', 'All Courses'
        COURSE = 'course', 'Specific Courses'
        CATEGORY = 'category', 'Category'
        BUNDLE = 'bundle', 'Specific Bundles'
        FIRST_PURCHASE = 'first_purchase', 'First Purchase Only'

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])

    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.GLOBAL)
    applicable_courses = models.ManyToManyField('course.Course', blank=True, related_name='coupons')
    applicable_categories = models.ManyToManyField('course.Category', blank=True, related_name='coupons')
    applicable_bundles = models.ManyToManyField('Bundle', blank=True, related_name='coupons')

    # Limits
    usage_limit = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    usage_limit_per_user = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    used_count = models.IntegerField(default=0)

    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()

    is_active = models.BooleanField(default=True)
    is_auto_apply = models.BooleanField(default=False)

    # Requirements
    minimum_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    new_users_only = models.BooleanField(default=False)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_coupons')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code', 'is_active']),
            models.Index(fields=['valid_from', 'valid_until']),
        ]

    def __str__(self):
        return f"{self.code} ({self.discount_type}: {self.discount_value})"

    def is_valid(self, user=None, order_amount=0, items=None):
        now = timezone.now()
        if not self.is_active:
            return False, "Coupon is not active."
        if now < self.valid_from:
            return False, "Coupon is not yet valid."
        if now > self.valid_until:
            return False, "Coupon has expired."
        if self.usage_limit > 0 and self.used_count >= self.usage_limit:
            return False, "Coupon usage limit reached."
        if order_amount < float(self.minimum_order_amount):
            return False, f"Minimum order amount is {self.minimum_order_amount}."
        if user and self.new_users_only and user.orders.filter(status=OrderStatus.COMPLETED).exists():
            return False, "Coupon is for new users only."
        return True, "Valid"

    def calculate_discount(self, order_amount, items=None):
        if self.discount_type == Coupon.DiscountType.PERCENTAGE:
            discount = order_amount * (float(self.discount_value) / 100)
        else:
            discount = float(self.discount_value)

        if self.max_discount_amount:
            discount = min(discount, float(self.max_discount_amount))

        return min(discount, order_amount)


class Bundle(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to='bundles/', null=True, blank=True)

    courses = models.ManyToManyField('course.Course', related_name='bundles')
    original_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    max_uses = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    used_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def discount_percentage(self):
        if self.original_price > 0:
            return round((1 - float(self.sale_price) / float(self.original_price)) * 100)
        return 0


class SubscriptionPlan(models.Model):
    class Interval(models.TextChoices):
        MONTHLY = 'monthly', 'Monthly'
        YEARLY = 'yearly', 'Yearly'
        QUARTERLY = 'quarterly', 'Quarterly'

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='USD')
    interval = models.CharField(max_length=20, choices=Interval.choices, default=Interval.MONTHLY)
    interval_count = models.IntegerField(default=1, validators=[MinValueValidator(1)])

    trial_days = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    setup_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])

    # Features
    features = models.JSONField(default=list, blank=True)
    max_courses = models.IntegerField(default=0)  # 0 = unlimited
    includes_bundles = models.BooleanField(default=False)

    # Stripe
    stripe_price_id = models.CharField(max_length=100, blank=True)
    stripe_product_id = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'price']

    def __str__(self):
        return f"{self.name} - {self.price}/{self.interval}"


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        TRIALING = 'trialing', 'Trialing'
        PAST_DUE = 'past_due', 'Past Due'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
        PAUSED = 'paused', 'Paused'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='subscriptions')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    # Stripe
    stripe_subscription_id = models.CharField(max_length=100, blank=True, db_index=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_payment_method_id = models.CharField(max_length=100, blank=True)

    # Pricing (snapshot)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    interval = models.CharField(max_length=20)

    # Dates
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    trial_end = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Cancellation
    cancel_at_period_end = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['stripe_subscription_id']),
        ]

    def __str__(self):
        return f"{self.user.display_name} - {self.plan.name} ({self.status})"

    @property
    def is_active_subscription(self):
        return self.status in [self.Status.ACTIVE, self.Status.TRIALING]

    @property
    def days_remaining(self):
        if self.current_period_end:
            delta = self.current_period_end - timezone.now()
            return max(0, delta.days)
        return 0


class SubscriptionInvoice(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='invoices')
    transaction = models.OneToOneField('transaction.Transaction', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscription_invoice')

    stripe_invoice_id = models.CharField(max_length=100, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')

    status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('void', 'Void'),
        ('uncollectible', 'Uncollectible'),
    ])

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice for {self.subscription} - {self.amount}"


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    class Reason(models.TextChoices):
        CUSTOMER_REQUEST = 'customer_request', 'Customer Request'
        DUPLICATE_CHARGE = 'duplicate_charge', 'Duplicate Charge'
        FRAUDULENT = 'fraudulent', 'Fraudulent'
        PRODUCT_UNACCEPTABLE = 'product_unacceptable', 'Product Unacceptable'
        OTHER = 'other', 'Other'

    transaction = models.ForeignKey('transaction.Transaction', on_delete=models.CASCADE, related_name='refunds')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refunds')

    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.CharField(max_length=30, choices=Reason.choices)
    reason_details = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    # Gateway
    gateway_refund_id = models.CharField(max_length=200, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    # Approval
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='requested_refunds')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_refunds')
    approved_at = models.DateTimeField(null=True, blank=True)

    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction', 'status']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"Refund {self.amount} for Transaction {self.transaction_id} ({self.status})"

    def approve(self, approved_by):
        self.status = Refund.Status.APPROVED
        self.approved_by = approved_by
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

    def process(self):
        self.status = Refund.Status.PROCESSING
        self.save(update_fields=['status', 'updated_at'])

    def complete(self):
        self.status = Refund.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

        # Update original transaction status
        original = self.transaction
        total_refunded = original.refunds.filter(
            status__in=[Refund.Status.COMPLETED, Refund.Status.PROCESSING]
        ).aggregate(total=models.Sum('amount'))['total'] or 0

        if total_refunded >= original.amount:
            original.status = 'refunded'
        else:
            original.status = 'partially_refunded'
        original.save(update_fields=['status', 'updated_at'])


class WebhookEvent(models.Model):
    gateway = models.CharField(max_length=20, choices=[
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('razorpay', 'Razorpay'),
        ('manual', 'Manual'),
    ])
    event_type = models.CharField(max_length=100)
    event_id = models.CharField(max_length=200, db_index=True)

    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('gateway', 'event_id')
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.gateway} - {self.event_type} ({self.event_id})"

    def mark_processed(self, error=None):
        self.processed = True
        self.processed_at = timezone.now()
        if error:
            self.processing_error = error
        self.save(update_fields=['processed', 'processed_at', 'processing_error'])


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'
    PARTIALLY_REFUNDED = 'partially_refunded', 'Partially Refunded'
    EXPIRED = 'expired', 'Expired'


class OrderType(models.TextChoices):
    COURSE_PURCHASE = 'course_purchase', 'Course Purchase'
    SUBSCRIPTION = 'subscription', 'Subscription'
    BUNDLE = 'bundle', 'Bundle Purchase'
    UPGRADE = 'upgrade', 'Upgrade'
    DONATION = 'donation', 'Donation'


class Order(models.Model):
    """Legacy Order model - kept for backwards compatibility. Use transaction.Transaction instead."""
    order_number = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')

    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.COURSE_PURCHASE)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING, db_index=True)

    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='USD')

    # Coupon
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    coupon_code = models.CharField(max_length=50, blank=True)

    # Payment
    gateway = models.CharField(max_length=20, choices=[
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('razorpay', 'Razorpay'),
        ('manual', 'Manual'),
    ])
    gateway_order_id = models.CharField(max_length=200, blank=True)
    gateway_payment_id = models.CharField(max_length=200, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    # Billing
    billing_email = models.EmailField()
    billing_name = models.CharField(max_length=200, blank=True)
    billing_address = models.JSONField(default=dict, blank=True)
    billing_country = models.CharField(max_length=2, blank=True)

    # Items (JSON for flexibility)
    items = models.JSONField(default=list)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Timestamps
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['gateway_order_id']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Order {self.order_number} - {self.user.display_name} - {self.total_amount} {self.currency}"

    def can_refund(self):
        return self.status == OrderStatus.COMPLETED and self.total_amount > 0

    def mark_completed(self):
        self.status = OrderStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_failed(self, reason=''):
        self.status = OrderStatus.FAILED
        self.failed_at = timezone.now()
        self.gateway_response['failure_reason'] = reason
        self.save(update_fields=['status', 'failed_at', 'gateway_response', 'updated_at'])


class OrderItem(models.Model):
    class ItemType(models.TextChoices):
        COURSE = 'course', 'Course'
        BUNDLE = 'bundle', 'Bundle'
        SUBSCRIPTION = 'subscription', 'Subscription'

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_items')
    item_type = models.CharField(max_length=20, choices=ItemType.choices)

    # References
    course = models.ForeignKey('course.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    bundle = models.ForeignKey(Bundle, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')

    # Pricing (snapshot at purchase time)
    name = models.CharField(max_length=300)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    total_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    # Teacher revenue share (for courses)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
    revenue_share_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    teacher_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.name} x{self.quantity} - {self.total_price}"