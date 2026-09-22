from django.contrib import admin

from .models import TeacherEarning, Payout, PayoutSchedule, RevenueReport


@admin.register(TeacherEarning)
class TeacherEarningAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'total_earned', 'pending_payout', 'available_for_payout', 'lifetime_payout', 'last_payout_at', 'stripe_onboarding_complete']
    list_filter = ['stripe_onboarding_complete', 'currency', 'created_at']
    search_fields = ['teacher__display_name', 'teacher__email', 'stripe_account_id']
    raw_id_fields = ['teacher']
    readonly_fields = ['total_earned', 'pending_payout', 'available_for_payout', 'lifetime_payout', 'last_payout_at', 'last_payout_amount', 'stripe_onboarding_complete', 'created_at', 'updated_at']
    ordering = ['-total_earned']

@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ['id', 'teacher', 'amount', 'net_amount', 'fee', 'status', 'method', 'period_start', 'period_end', 'requested_at', 'paid_at']
    list_filter = ['status', 'method', 'currency', 'requested_at', 'paid_at']
    search_fields = ['teacher__display_name', 'teacher__email', 'stripe_payout_id', 'bank_transfer_id']
    raw_id_fields = ['teacher', 'earning']
    filter_horizontal = ['transactions']
    readonly_fields = ['requested_at', 'processed_at', 'paid_at', 'created_at', 'updated_at']
    ordering = ['-requested_at']
    list_per_page = 50

    actions = ['mark_processing', 'mark_paid', 'mark_failed']

    def mark_processing(self, request, queryset):
        queryset.filter(status=Payout.Status.PENDING).update(status=Payout.Status.PROCESSING)
    mark_processing.short_description = "Mark selected payouts as processing"

    def mark_paid(self, request, queryset):
        for payout in queryset.filter(status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING]):
            payout.mark_paid()
    mark_paid.short_description = "Mark selected payouts as paid"

    def mark_failed(self, request, queryset):
        queryset.filter(status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING]).update(status=Payout.Status.FAILED, failure_reason='Manual failure by admin')
    mark_failed.short_description = "Mark selected payouts as failed"


@admin.register(PayoutSchedule)
class PayoutScheduleAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'schedule', 'day_of_week', 'day_of_month', 'minimum_amount', 'auto_payout', 'next_run_at']
    list_filter = ['schedule', 'auto_payout']
    search_fields = ['teacher__display_name', 'teacher__email']
    raw_id_fields = ['teacher']
    readonly_fields = ['last_run_at', 'next_run_at']


@admin.register(RevenueReport)
class RevenueReportAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'period_start', 'period_end', 'gross_revenue', 'net_revenue', 'sales_count', 'generated_at']
    list_filter = ['generated_at', 'period_start']
    search_fields = ['teacher__display_name', 'teacher__email']
    raw_id_fields = ['teacher']
    readonly_fields = ['generated_at']
    ordering = ['-period_start']