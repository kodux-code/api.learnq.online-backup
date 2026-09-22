from rest_framework import serializers
from .models import (
    NotificationTemplate, NotificationPreference, Notification,
    NotificationBatch, DeviceToken, PushNotificationLog,
    EmailNotificationLog, InAppNotificationGroup
)
from client.serializers import PublicProfileSerializer


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'name', 'slug', 'description',
            'subject_template', 'body_template', 'html_template',
            'push_title_template', 'push_body_template',
            'available_variables', 'required_variables', 'channels',
            'is_active', 'is_system',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationTemplateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = [
            'name', 'slug', 'description',
            'subject_template', 'body_template', 'html_template',
            'push_title_template', 'push_body_template',
            'available_variables', 'required_variables', 'channels',
            'is_active'
        ]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'in_app_enabled', 'email_enabled', 'push_enabled', 'sms_enabled',
            'category_preferences', 'quiet_hours_enabled',
            'quiet_hours_start', 'quiet_hours_end', 'timezone',
            'digest_frequency',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class NotificationSerializer(serializers.ModelSerializer):
    sender = PublicProfileSerializer(read_only=True)
    template = NotificationTemplateSerializer(read_only=True)
    content_object = serializers.SerializerMethodField()
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'sender', 'template', 'title', 'message', 'html_message',
            'category', 'action_url', 'action_text', 'icon', 'color',
            'priority', 'channels',
            'content_type', 'object_id', 'content_object',
            'status', 'sent_at', 'delivered_at', 'read_at', 'archived_at',
            'metadata', 'created_at', 'updated_at', 'is_read'
        ]
        read_only_fields = [
            'id', 'sender', 'template', 'title', 'message', 'html_message',
            'category', 'action_url', 'action_text', 'icon', 'color',
            'priority', 'channels', 'content_type', 'object_id',
            'status', 'sent_at', 'delivered_at', 'read_at', 'archived_at',
            'metadata', 'created_at', 'updated_at'
        ]

    def get_content_object(self, obj):
        if obj.content_object:
            return {
                'type': obj.content_type.model,
                'id': str(obj.object_id),
                'title': str(obj.content_object)
            }
        return None

    def get_is_read(self, obj):
        return obj.status == Notification.Status.READ


class NotificationListSerializer(serializers.ModelSerializer):
    sender = PublicProfileSerializer(read_only=True)
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'sender', 'title', 'message',
            'category', 'action_url', 'action_text', 'icon', 'color',
            'priority', 'status', 'is_read',
            'created_at'
        ]


class NotificationCreateSerializer(serializers.ModelSerializer):
    recipient_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    recipient_filter = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Notification
        fields = [
            'recipient_ids', 'recipient_filter',
            'template', 'title', 'message', 'html_message',
            'category', 'action_url', 'action_text', 'icon', 'color',
            'priority', 'channels',
            'content_type', 'object_id',
            'metadata'
        ]

    def validate(self, attrs):
        if not attrs.get('recipient_ids') and not attrs.get('recipient_filter'):
            raise serializers.ValidationError("Either recipient_ids or recipient_filter is required.")
        return attrs


class NotificationBatchSerializer(serializers.ModelSerializer):
    template = NotificationTemplateSerializer(read_only=True)
    created_by = PublicProfileSerializer(read_only=True)

    class Meta:
        model = NotificationBatch
        fields = [
            'id', 'template', 'name', 'description',
            'recipient_filter', 'recipient_count',
            'status', 'scheduled_at', 'started_at', 'completed_at',
            'sent_count', 'failed_count', 'channels',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'recipient_count', 'status', 'started_at', 'completed_at',
            'sent_count', 'failed_count', 'created_by', 'created_at', 'updated_at'
        ]


class NotificationBatchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationBatch
        fields = [
            'template', 'name', 'description',
            'recipient_filter', 'scheduled_at', 'channels'
        ]


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = [
            'id', 'token', 'platform', 'device_id', 'device_name',
            'app_version', 'os_version', 'is_active', 'last_used_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_used_at', 'created_at', 'updated_at']


class DeviceTokenRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ['token', 'platform', 'device_id', 'device_name', 'app_version', 'os_version']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        device, created = DeviceToken.objects.update_or_create(
            user=validated_data['user'],
            token=validated_data['token'],
            defaults=validated_data
        )
        return device


class PushNotificationLogSerializer(serializers.ModelSerializer):
    notification_title = serializers.CharField(source='notification.title', read_only=True)

    class Meta:
        model = PushNotificationLog
        fields = [
            'id', 'notification', 'notification_title', 'device_token',
            'status', 'provider', 'provider_message_id', 'error_message',
            'sent_at', 'delivered_at', 'clicked_at'
        ]
        read_only_fields = fields


class EmailNotificationLogSerializer(serializers.ModelSerializer):
    notification_title = serializers.CharField(source='notification.title', read_only=True)

    class Meta:
        model = EmailNotificationLog
        fields = [
            'id', 'notification', 'notification_title',
            'status', 'provider', 'provider_message_id', 'error_message',
            'recipient_email', 'subject',
            'sent_at', 'delivered_at', 'opened_at', 'clicked_at'
        ]
        read_only_fields = fields


class InAppNotificationGroupSerializer(serializers.ModelSerializer):
    last_notification = NotificationListSerializer(read_only=True)

    class Meta:
        model = InAppNotificationGroup
        fields = ['category', 'count', 'last_notification', 'is_expanded', 'updated_at']


class NotificationStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    unread = serializers.IntegerField()
    by_category = serializers.DictField(child=serializers.IntegerField())
    by_priority = serializers.DictField(child=serializers.IntegerField())
    by_channel = serializers.DictField(child=serializers.IntegerField())