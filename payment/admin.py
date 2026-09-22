from django.contrib import admin
from .models import (
    Order, OrderItem, Bundle, Coupon,
    SubscriptionPlan, Subscription, SubscriptionInvoice,
    Refund, WebhookEvent
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ['course', 'bundle', 'subscription', 'teacher']
    readonly_fields = ['teacher_amount']
    fields = ['item_type', 'course', 'bundle', 'subscription', 'name', 'unit_price', 'quantity', 'total_price', 'teacher', 'revenue_share_percent', 'teacher_amount']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'user', 'order_type', 'status', 'total_amount', 'currency', 'gateway', 'completed_at', 'created_at']
    list_filter = ['order_type', 'status', 'gateway', 'currency', 'created_at', 'completed_at']
    search_fields = ['order_number', 'user__display_name', 'user__email', 'gateway_order_id', 'gateway_payment_id', 'billing_email']
    raw_id_fields = ['user', 'coupon']
    readonly_fields = ['order_number', 'completed_at', 'failed_at', 'cancelled_at', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 25
    inlines = [OrderItemInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {'fields': ('order_number', 'user', 'order_type', 'status')}),
        ('Pricing', {'fields': ('subtotal', 'tax_amount', 'discount_amount', 'total_amount', 'currency')}),
        ('Coupon', {'fields': ('coupon', 'coupon_code')}),
        ('Payment', {'fields': ('gateway', 'gateway_order_id', 'gateway_payment_id', 'gateway_response')}),
        ('Billing', {'fields': ('billing_email', 'billing_name', 'billing_address', 'billing_country')}),
        ('Items', {'fields': ('items',)}),
        ('Metadata', {'fields': ('metadata', 'ip_address', 'user_agent'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('completed_at', 'failed_at', 'cancelled_at', 'expires_at', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    actions = ['mark_completed', 'mark_failed']

    def mark_completed(self, request, queryset):
        for order in queryset.filter(status=Order.Status.PENDING):
            order.mark_completed()
    mark_completed.short_description = "Mark selected orders as completed"

    def mark_failed(self, request, queryset):
        for order in queryset.filter(status=Order.Status.PENDING):
            order.mark_failed('Manual failure by admin')
    mark_failed.short_description = "Mark selected orders as failed"


@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'course_count', 'original_price', 'sale_price', 'discount_percentage', 'is_active', 'is_featured', 'valid_until', 'used_count']
    list_filter = ['is_active', 'is_featured', 'valid_from', 'valid_until']
    search_fields = ['title', 'slug', 'description']
    filter_horizontal = ['courses']
    readonly_fields = ['used_count', 'created_at', 'updated_at']
    ordering = ['-is_featured', '-created_at']

    def course_count(self, obj):
        return obj.courses.count()
    course_count.short_description = 'Courses'


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'discount_type', 'discount_value', 'scope', 'usage_limit', 'used_count', 'is_active', 'valid_from', 'valid_until']
    list_filter = ['discount_type', 'scope', 'is_active', 'is_auto_apply', 'new_users_only', 'valid_from', 'valid_until']
    search_fields = ['code', 'name', 'description']
    filter_horizontal = ['applicable_courses', 'applicable_categories', 'applicable_bundles']
    raw_id_fields = ['created_by']
    readonly_fields = ['used_count', 'created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        (None, {'fields': ('code', 'name', 'description')}),
        ('Discount', {'fields': ('discount_type', 'discount_value', 'max_discount_amount')}),
        ('Scope', {'fields': ('scope', 'applicable_courses', 'applicable_categories', 'applicable_bundles')}),
        ('Limits', {'fields': ('usage_limit', 'usage_limit_per_user', 'used_count')}),
        ('Validity', {'fields': ('valid_from', 'valid_until', 'is_active', 'is_auto_apply', 'minimum_order_amount', 'new_users_only')}),
        ('Meta', {'fields': ('created_by', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'price', 'currency', 'interval', 'interval_count', 'trial_days', 'is_active', 'is_featured', 'sort_order']
    list_filter = ['interval', 'is_active', 'is_featured']
    search_fields = ['name', 'slug', 'description']
    readonly_fields = ['stripe_price_id', 'stripe_product_id', 'created_at', 'updated_at']
    ordering = ['sort_order', 'price']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'status', 'price', 'currency', 'current_period_end', 'cancel_at_period_end', 'created_at']
    list_filter = ['status', 'plan', 'currency', 'cancel_at_period_end', 'created_at']
    search_fields = ['user__display_name', 'user__email', 'plan__name', 'stripe_subscription_id', 'stripe_customer_id']
    raw_id_fields = ['user', 'plan']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 50
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {'fields': ('user', 'plan', 'status')}),
        ('Pricing', {'fields': ('price', 'currency', 'interval')}),
        ('Stripe', {'fields': ('stripe_subscription_id', 'stripe_customer_id', 'stripe_payment_method_id')}),
        ('Dates', {'fields': ('current_period_start', 'current_period_end', 'trial_end', 'cancelled_at', 'ended_at')}),
        ('Cancellation', {'fields': ('cancel_at_period_end', 'cancellation_reason')}),
        ('Metadata', {'fields': ('metadata',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(admin.ModelAdmin):
    list_display = ['subscription', 'stripe_invoice_id', 'amount', 'currency', 'status', 'period_start', 'period_end', 'paid_at']
    list_filter = ['status', 'currency', 'paid_at']
    search_fields = ['subscription__user__display_name', 'stripe_invoice_id']
    raw_id_fields = ['subscription', 'transaction']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ['id', 'transaction', 'user', 'amount', 'reason', 'status', 'requested_by', 'approved_by', 'created_at']
    list_filter = ['status', 'reason', 'created_at', 'approved_at', 'completed_at']
    search_fields = ['transaction__order__order_number', 'user__display_name', 'user__email', 'gateway_refund_id']
    raw_id_fields = ['transaction', 'user', 'requested_by', 'approved_by']
    readonly_fields = ['gateway_response', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 50

    actions = ['approve_refunds', 'reject_refunds']

    def approve_refunds(self, request, queryset):
        for refund in queryset.filter(status=Refund.Status.PENDING):
            refund.approve(request.user)
    approve_refunds.short_description = "Approve selected refunds"

    def reject_refunds(self, request, queryset):
        queryset.filter(status=Refund.Status.PENDING).update(status=Refund.Status.REJECTED)
    reject_refunds.short_description = "Reject selected refunds"


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ['gateway', 'event_type', 'event_id', 'processed', 'received_at', 'processed_at']
    list_filter = ['gateway', 'processed', 'received_at']
    search_fields = ['event_id', 'event_type']
    readonly_fields = ['payload', 'received_at', 'processed_at', 'processing_error']
    ordering = ['-received_at']
    list_per_page = 100

    def has_add_permission(self, request):
        return False
