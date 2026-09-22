from django.contrib import admin
from .models import (
    NotificationTemplate, NotificationPreference, Notification,
    NotificationBatch, DeviceToken, PushNotificationLog,
    EmailNotificationLog, InAppNotificationGroup
)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'channels', 'is_active', 'is_system', 'created_at']
    list_filter = ['is_active', 'is_system', 'channels', 'created_at']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['name']

    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description', 'channels')}),
        ('Templates', {'fields': ('subject_template', 'body_template', 'html_template', 'push_title_template', 'push_body_template')}),
        ('Variables', {'fields': ('available_variables', 'required_variables'), 'classes': ('collapse',)}),
        ('Settings', {'fields': ('is_active', 'is_system')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'in_app_enabled', 'email_enabled', 'push_enabled', 'sms_enabled', 'digest_frequency', 'quiet_hours_enabled']
    list_filter = ['in_app_enabled', 'email_enabled', 'push_enabled', 'sms_enabled', 'digest_frequency', 'quiet_hours_enabled']
    search_fields = ['user__display_name', 'user__email']
    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'recipient', 'sender', 'category', 'priority', 'status', 'channels', 'created_at']
    list_filter = ['status', 'priority', 'category', 'channels', 'created_at', 'template']
    search_fields = ['title', 'message', 'recipient__display_name', 'recipient__email', 'sender__display_name']
    raw_id_fields = ['recipient', 'sender', 'template', 'content_type']
    readonly_fields = ['sent_at', 'delivered_at', 'read_at', 'archived_at', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 50
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {'fields': ('recipient', 'sender', 'template')}),
        ('Content', {'fields': ('title', 'message', 'html_message', 'category', 'action_url', 'action_text', 'icon', 'color')}),
        ('Delivery', {'fields': ('priority', 'channels', 'status', 'error_message', 'retry_count')}),
        ('Related Object', {'fields': ('content_type', 'object_id'), 'classes': ('collapse',)}),
        ('Metadata', {'fields': ('metadata',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('sent_at', 'delivered_at', 'read_at', 'archived_at', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(NotificationBatch)
class NotificationBatchAdmin(admin.ModelAdmin):
    list_display = ['name', 'template', 'status', 'recipient_count', 'sent_count', 'failed_count', 'scheduled_at', 'created_by', 'created_at']
    list_filter = ['status', 'template', 'created_at']
    search_fields = ['name', 'template__name', 'created_by__display_name']
    raw_id_fields = ['template', 'created_by']
    readonly_fields = ['recipient_count', 'sent_count', 'failed_count', 'started_at', 'completed_at', 'created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        (None, {'fields': ('template', 'name', 'description')}),
        ('Recipients', {'fields': ('recipient_filter', 'recipient_count')}),
        ('Scheduling', {'fields': ('status', 'scheduled_at', 'channels')}),
        ('Results', {'fields': ('sent_count', 'failed_count', 'started_at', 'completed_at')}),
        ('Meta', {'fields': ('created_by', 'created_at', 'updated_at')}),
    )

    actions = ['send_now']

    def send_now(self, request, queryset):
        for batch in queryset.filter(status__in=[NotificationBatch.Status.PENDING, NotificationBatch.Status.FAILED]):
            batch.status = NotificationBatch.Status.PENDING
            batch.scheduled_at = None
            batch.save()
            # Would trigger Celery task in production
        self.message_user(request, f'Queued {queryset.count()} batches for sending.')
    send_now.short_description = "Send selected batches now"


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'platform', 'device_name', 'is_active', 'last_used_at', 'created_at']
    list_filter = ['platform', 'is_active', 'created_at']
    search_fields = ['user__display_name', 'user__email', 'token', 'device_id']
    raw_id_fields = ['user']
    readonly_fields = ['last_used_at', 'created_at', 'updated_at']
    ordering = ['-last_used_at']


@admin.register(PushNotificationLog)
class PushNotificationLogAdmin(admin.ModelAdmin):
    list_display = ['notification', 'device_token', 'status', 'provider', 'sent_at', 'delivered_at', 'clicked_at']
    list_filter = ['status', 'provider', 'sent_at']
    search_fields = ['notification__title', 'device_token__user__display_name', 'provider_message_id']
    raw_id_fields = ['notification', 'device_token']
    readonly_fields = ['sent_at', 'delivered_at', 'clicked_at']
    ordering = ['-sent_at']
    list_per_page = 100


@admin.register(EmailNotificationLog)
class EmailNotificationLogAdmin(admin.ModelAdmin):
    list_display = ['subject', 'recipient_email', 'status', 'provider', 'sent_at', 'delivered_at', 'opened_at', 'clicked_at']
    list_filter = ['status', 'provider', 'sent_at']
    search_fields = ['subject', 'recipient_email', 'provider_message_id']
    raw_id_fields = ['notification']
    readonly_fields = ['sent_at', 'delivered_at', 'opened_at', 'clicked_at']
    ordering = ['-sent_at']
    list_per_page = 100


@admin.register(InAppNotificationGroup)
class InAppNotificationGroupAdmin(admin.ModelAdmin):
    list_display = ['user', 'category', 'count', 'is_expanded', 'updated_at']
    list_filter = ['category', 'is_expanded']
    search_fields = ['user__display_name', 'user__email']
    raw_id_fields = ['user', 'last_notification']
    readonly_fields = ['updated_at']
    ordering = ['-updated_at']