from rest_framework import serializers
from django.db.models import Sum, Avg, Count, F
from django.utils import timezone
from datetime import timedelta

from message.serializers import MinimalUserSerializer
from .models import (
    Event, DailyMetric, HourlyMetric, Dashboard, DashboardWidget,
    Report, RetentionCohort, FunnelStep, Alert, AlertTrigger, AnalyticsSettings
)


class EventSerializer(serializers.ModelSerializer):
    user = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = Event
        fields = [
            'id', 'event_type', 'user', 'session_id', 'properties',
            'ip_address', 'user_agent', 'referrer', 'url',
            'source_app', 'source_version', 'timestamp', 'received_at'
        ]
        read_only_fields = fields


class EventCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            'event_type', 'session_id', 'properties',
            'ip_address', 'user_agent', 'referrer', 'url',
            'source_app', 'source_version'
        ]
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user if self.context['request'].user.is_authenticated else None
        return super().create(validated_data)


class BatchEventSerializer(serializers.Serializer):
    events = EventCreateSerializer(many=True)


class DailyMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyMetric
        fields = [
            'date', 'metric_name', 'metric_type', 'app', 'user_role',
            'country', 'device_type', 'dimension_key', 'dimension_value',
            'count', 'sum_value', 'min_value', 'max_value', 'avg_value',
            'percentiles', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class HourlyMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = HourlyMetric
        fields = ['hour', 'metric_name', 'app', 'count', 'sum_value', 'created_at']
        read_only_fields = fields


class DashboardWidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardWidget
        fields = [
            'id', 'widget_type', 'title', 'description',
            'metric_names', 'dimensions', 'filters', 'time_range', 'granularity',
            'chart_options', 'colors', 'x', 'y', 'width', 'height', 'is_visible',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DashboardSerializer(serializers.ModelSerializer):
    widgets = DashboardWidgetSerializer(many=True, read_only=True)
    owner = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = Dashboard
        fields = [
            'id', 'owner', 'name', 'description', 'is_default', 'is_public',
            'layout', 'filters', 'widgets', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']


class DashboardCreateSerializer(serializers.ModelSerializer):
    widgets = DashboardWidgetSerializer(many=True, required=False)
    
    class Meta:
        model = Dashboard
        fields = ['name', 'description', 'is_default', 'is_public', 'layout', 'filters', 'widgets']
    
    def create(self, validated_data):
        widgets_data = validated_data.pop('widgets', [])
        validated_data['owner'] = self.context['request'].user
        dashboard = Dashboard.objects.create(**validated_data)
        for widget_data in widgets_data:
            DashboardWidget.objects.create(dashboard=dashboard, **widget_data)
        return dashboard
    
    def update(self, instance, validated_data):
        widgets_data = validated_data.pop('widgets', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if widgets_data is not None:
            instance.widgets.all().delete()
            for widget_data in widgets_data:
                DashboardWidget.objects.create(dashboard=instance, **widget_data)
        return instance


class ReportSerializer(serializers.ModelSerializer):
    owner = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = Report
        fields = [
            'id', 'owner', 'name', 'description', 'format', 'status',
            'query', 'is_scheduled', 'schedule_cron', 'schedule_timezone',
            'last_generated_at', 'next_run_at', 'file', 'file_size',
            'row_count', 'error_message', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'owner', 'status', 'last_generated_at', 'next_run_at',
            'file', 'file_size', 'row_count', 'error_message', 'created_at', 'updated_at'
        ]


class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['name', 'description', 'format', 'query', 'is_scheduled', 'schedule_cron', 'schedule_timezone']
    
    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class RetentionCohortSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetentionCohort
        fields = [
            'cohort_date', 'cohort_size', 'period', 'period_type',
            'retained_users', 'retention_rate', 'app', 'user_role',
            'acquisition_channel', 'calculated_at'
        ]
        read_only_fields = fields


class FunnelStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunnelStep
        fields = ['id', 'funnel_name', 'step_order', 'step_name', 'event_type', 'filters']


class FunnelAnalysisSerializer(serializers.Serializer):
    funnel_name = serializers.CharField()
    steps = serializers.ListField(child=serializers.DictField())
    conversion_rates = serializers.ListField(child=serializers.FloatField())
    drop_off_rates = serializers.ListField(child=serializers.FloatField())
    total_conversion_rate = serializers.FloatField()


class AlertSerializer(serializers.ModelSerializer):
    notify_users = MinimalUserSerializer(many=True, read_only=True)
    notify_user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Alert
        fields = [
            'id', 'name', 'description', 'metric_name', 'condition',
            'severity', 'status', 'notify_channels', 'notify_users',
            'notify_user_ids', 'cooldown_minutes', 'last_triggered_at',
            'trigger_count', 'is_enabled', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_triggered_at', 'trigger_count', 'created_at', 'updated_at']


class AlertTriggerSerializer(serializers.ModelSerializer):
    acknowledged_by = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = AlertTrigger
        fields = [
            'id', 'alert', 'triggered_at', 'metric_value', 'threshold_value',
            'context', 'acknowledged_at', 'acknowledged_by', 'resolved_at'
        ]
        read_only_fields = fields


class AlertActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['acknowledge', 'resolve'])


class AnalyticsSettingsSerializer(serializers.ModelSerializer):
    updated_by = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = AnalyticsSettings
        fields = ['key', 'value', 'description', 'updated_at', 'updated_by']
        read_only_fields = ['key', 'updated_at', 'updated_by']


class TimeSeriesQuerySerializer(serializers.Serializer):
    metric_names = serializers.ListField(child=serializers.CharField(), required=True)
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    granularity = serializers.ChoiceField(choices=['hour', 'day', 'week', 'month'], default='day')
    dimensions = serializers.DictField(required=False, default=dict)
    filters = serializers.DictField(required=False, default=dict)
    apps = serializers.ListField(child=serializers.CharField(), required=False)
    user_roles = serializers.ListField(child=serializers.CharField(), required=False)
    
    def validate(self, attrs):
        if attrs['start_date'] > attrs['end_date']:
            raise serializers.ValidationError("start_date must be before end_date")
        if (attrs['end_date'] - attrs['start_date']).days > 365:
            raise serializers.ValidationError("Date range cannot exceed 365 days")
        return attrs


class TimeSeriesDataSerializer(serializers.Serializer):
    metric_name = serializers.CharField()
    granularity = serializers.CharField()
    data = serializers.ListField(child=serializers.DictField())


class RealtimeMetricsSerializer(serializers.Serializer):
    active_users = serializers.IntegerField()
    events_per_minute = serializers.IntegerField()
    revenue_per_minute = serializers.DecimalField(max_digits=12, decimal_places=2)
    top_events = serializers.ListField(child=serializers.DictField())
    top_pages = serializers.ListField(child=serializers.DictField())
    errors_per_minute = serializers.IntegerField()
    avg_response_time = serializers.FloatField()


class CohortAnalysisSerializer(serializers.Serializer):
    cohorts = RetentionCohortSerializer(many=True)
    summary = serializers.DictField()


class UserJourneySerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    events = EventSerializer(many=True)
    session_duration = serializers.IntegerField()
    pages_visited = serializers.IntegerField()
    conversions = serializers.ListField(child=serializers.DictField())
