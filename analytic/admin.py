from django.contrib import admin
from .models import (
    Event, DailyMetric, HourlyMetric, Dashboard, DashboardWidget,
    Report, RetentionCohort, FunnelStep, Alert, AlertTrigger, AnalyticsSettings
)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'user', 'source_app', 'timestamp', 'session_id']
    list_filter = ['event_type', 'source_app', 'timestamp']
    search_fields = ['user__display_name', 'user__email', 'session_id', 'event_type', 'properties']
    raw_id_fields = ['user']
    readonly_fields = ['timestamp', 'received_at']
    ordering = ['-timestamp']
    list_per_page = 100
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    list_display = ['date', 'metric_name', 'app', 'user_role', 'country', 'count', 'sum_value', 'avg_value']
    list_filter = ['metric_name', 'app', 'user_role', 'country', 'device_type', 'date']
    search_fields = ['metric_name', 'dimension_key', 'dimension_value']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-date', 'metric_name']
    list_per_page = 50
    date_hierarchy = 'date'
    
    def has_add_permission(self, request):
        return False


@admin.register(HourlyMetric)
class HourlyMetricAdmin(admin.ModelAdmin):
    list_display = ['hour', 'metric_name', 'app', 'count', 'sum_value']
    list_filter = ['metric_name', 'app', 'hour']
    readonly_fields = ['created_at']
    ordering = ['-hour']
    list_per_page = 50
    date_hierarchy = 'hour'
    
    def has_add_permission(self, request):
        return False


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'is_default', 'is_public', 'widget_count', 'updated_at']
    list_filter = ['is_default', 'is_public', 'created_at']
    search_fields = ['name', 'description', 'owner__display_name', 'owner__email']
    raw_id_fields = ['owner']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']
    
    def widget_count(self, obj):
        return obj.widgets.count()
    widget_count.short_description = 'Widgets'


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ['dashboard', 'widget_type', 'title', 'metric_names', 'is_visible']
    list_filter = ['widget_type', 'is_visible', 'dashboard__owner']
    search_fields = ['title', 'dashboard__name']
    raw_id_fields = ['dashboard']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'format', 'status', 'row_count', 'is_scheduled', 'last_generated_at']
    list_filter = ['format', 'status', 'is_scheduled', 'created_at']
    search_fields = ['name', 'description', 'owner__display_name']
    raw_id_fields = ['owner']
    readonly_fields = ['last_generated_at', 'next_run_at', 'file', 'file_size', 'row_count', 'error_message', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    actions = ['trigger_generation']
    
    def trigger_generation(self, request, queryset):
        for report in queryset.filter(status__in=[Report.Status.PENDING, Report.Status.FAILED, Report.Status.COMPLETED]):
            report.status = Report.Status.GENERATING
            report.save()
    trigger_generation.short_description = "Regenerate selected reports"


@admin.register(RetentionCohort)
class RetentionCohortAdmin(admin.ModelAdmin):
    list_display = ['cohort_date', 'period', 'period_type', 'app', 'user_role', 'cohort_size', 'retained_users', 'retention_rate']
    list_filter = ['period_type', 'app', 'user_role', 'cohort_date']
    readonly_fields = ['calculated_at']
    ordering = ['-cohort_date', 'period']


@admin.register(FunnelStep)
class FunnelStepAdmin(admin.ModelAdmin):
    list_display = ['funnel_name', 'step_order', 'step_name', 'event_type']
    list_filter = ['funnel_name']
    search_fields = ['funnel_name', 'step_name']
    ordering = ['funnel_name', 'step_order']


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['name', 'metric_name', 'severity', 'status', 'is_enabled', 'trigger_count', 'last_triggered_at']
    list_filter = ['severity', 'status', 'is_enabled']
    search_fields = ['name', 'metric_name']
    raw_id_fields = ['notify_users']
    readonly_fields = ['last_triggered_at', 'trigger_count', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(AlertTrigger)
class AlertTriggerAdmin(admin.ModelAdmin):
    list_display = ['alert', 'triggered_at', 'metric_value', 'threshold_value', 'acknowledged_at', 'resolved_at']
    list_filter = ['alert__severity', 'alert__status']
    raw_id_fields = ['alert', 'acknowledged_by']
    readonly_fields = ['triggered_at', 'metric_value', 'threshold_value', 'context']
    ordering = ['-triggered_at']
    date_hierarchy = 'triggered_at'
    
    def has_add_permission(self, request):
        return False


@admin.register(AnalyticsSettings)
class AnalyticsSettingsAdmin(admin.ModelAdmin):
    list_display = ['key', 'description', 'updated_at', 'updated_by']
    search_fields = ['key', 'description']
    raw_id_fields = ['updated_by']
    readonly_fields = ['updated_at']
    
    def has_delete_permission(self, request, obj=None):
        return False