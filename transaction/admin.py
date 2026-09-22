from django.contrib import admin
from .models import Transaction, Wallet, WalletTransaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'teacher', 'direction', 'transaction_type', 'status', 'amount', 'currency', 'net_amount', 'teacher_amount', 'course', 'gateway', 'created_at']
    list_filter = ['direction', 'transaction_type', 'status', 'gateway', 'currency', 'created_at']
    search_fields = ['id', 'user__display_name', 'user__email', 'teacher__display_name', 'teacher__email', 'course__title', 'gateway_transaction_id', 'gateway_transfer_id']
    raw_id_fields = ['user', 'counterparty', 'teacher', 'course', 'enrollment', 'assessment', 'order', 'subscription', 'bundle', 'payout', 'coupon']
    readonly_fields = ['completed_at', 'failed_at', 'cancelled_at', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 50
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {'fields': ('id', 'user', 'counterparty', 'teacher', 'direction', 'transaction_type', 'status')}),
        ('Amounts', {'fields': ('amount', 'currency', 'net_amount', 'platform_fee', 'revenue_share_percent', 'teacher_amount')}),
        ('Related Objects', {'fields': ('course', 'enrollment', 'assessment', 'order', 'subscription', 'bundle', 'payout', 'coupon')}),
        ('Gateway', {'fields': ('gateway', 'gateway_transaction_id', 'gateway_transfer_id', 'gateway_payout_id', 'gateway_response', 'payout_method')}),
        ('Billing', {'fields': ('billing_email', 'billing_name', 'billing_address', 'billing_country', 'ip_address', 'user_agent')}),
        ('Discounts', {'fields': ('coupon_code', 'discount_amount')}),
        ('Metadata', {'fields': ('description', 'metadata'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('completed_at', 'failed_at', 'cancelled_at', 'expires_at', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    actions = ['mark_completed', 'mark_failed', 'reverse']
    
    def mark_completed(self, request, queryset):
        for txn in queryset.filter(status=Transaction.Status.PENDING):
            txn.mark_completed()
    mark_completed.short_description = "Mark selected transactions as completed"
    
    def mark_failed(self, request, queryset):
        for txn in queryset.filter(status=Transaction.Status.PENDING):
            txn.mark_failed('Manual failure by admin')
    mark_failed.short_description = "Mark selected transactions as failed"
    
    def reverse(self, request, queryset):
        for txn in queryset.filter(status=Transaction.Status.COMPLETED):
            txn.mark_reversed()
    reverse.short_description = "Reverse selected completed transactions"


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'currency', 'is_active', 'created_at']
    list_filter = ['currency', 'is_active']
    search_fields = ['user__display_name', 'user__email']
    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['wallet', 'type', 'amount', 'balance_before', 'balance_after', 'reference_id', 'created_at']
    list_filter = ['type', 'reference_type', 'created_at']
    search_fields = ['wallet__user__display_name', 'reference_id', 'description']
    raw_id_fields = ['wallet']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    list_per_page = 100