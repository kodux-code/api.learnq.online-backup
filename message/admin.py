from django.contrib import admin
from .models import Thread, ThreadParticipant, Message, ThreadInvite, MessageReadReceipt, MessageDeliveryReceipt


class ThreadParticipantInline(admin.TabularInline):
    model = ThreadParticipant
    extra = 0
    raw_id_fields = ['user']
    readonly_fields = ['joined_at', 'last_read_at', 'last_delivered_at']
    fields = ['user', 'role', 'is_active', 'is_muted', 'notifications_enabled', 'joined_at', 'last_read_at', 'last_delivered_at']


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    raw_id_fields = ['sender', 'reply_to']
    readonly_fields = ['created_at', 'updated_at', 'is_edited', 'edited_at', 'is_deleted', 'deleted_at']
    fields = ['sender', 'message_type', 'content', 'reply_to', 'is_system_message', 'system_event_type', 'is_deleted', 'created_at']
    ordering = ['-created_at']
    max_num = 50


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ['id', 'thread_type', 'name', 'participant_count', 'message_count', 'last_message_at', 'is_active', 'created_at']
    list_filter = ['thread_type', 'is_active', 'allows_reactions', 'created_at']
    search_fields = ['name', 'participants__user__display_name', 'participants__user__email']
    raw_id_fields = ['last_message']
    readonly_fields = ['created_at', 'updated_at', 'last_message_at']
    ordering = ['-last_message_at', '-created_at']
    inlines = [ThreadParticipantInline]
    list_per_page = 25

    def participant_count(self, obj):
        return obj.participants.filter(is_active=True).count()
    participant_count.short_description = 'Participants'

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'


@admin.register(ThreadParticipant)
class ThreadParticipantAdmin(admin.ModelAdmin):
    list_display = ['thread', 'user', 'role', 'is_active', 'is_muted', 'notifications_enabled', 'last_read_at', 'joined_at']
    list_filter = ['role', 'is_active', 'is_muted', 'notifications_enabled', 'joined_at']
    search_fields = ['thread__name', 'user__display_name', 'user__email']
    raw_id_fields = ['thread', 'user']
    readonly_fields = ['joined_at', 'last_read_at', 'last_delivered_at']
    ordering = ['-joined_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'thread', 'sender', 'message_type', 'preview', 'is_edited', 'is_deleted', 'is_system_message', 'created_at']
    list_filter = ['message_type', 'is_edited', 'is_deleted', 'is_system_message', 'created_at']
    search_fields = ['content', 'sender__display_name', 'thread__name', 'thread__id']
    raw_id_fields = ['thread', 'sender', 'reply_to', 'deleted_by']
    readonly_fields = ['created_at', 'updated_at', 'edited_at', 'deleted_at']
    ordering = ['-created_at']
    list_per_page = 50
    date_hierarchy = 'created_at'

    def preview(self, obj):
        if obj.is_deleted:
            return "[Deleted]"
        if obj.is_system_message:
            return f"[System] {obj.content[:50]}"
        return obj.content[:50] or f"[{obj.get_message_type_display()}]"
    preview.short_description = 'Preview'


@admin.register(ThreadInvite)
class ThreadInviteAdmin(admin.ModelAdmin):
    list_display = ['id', 'thread', 'invited_by', 'invited_user', 'status', 'created_at', 'responded_at']
    list_filter = ['status', 'created_at']
    search_fields = ['thread__name', 'invited_by__display_name', 'invited_user__display_name']
    raw_id_fields = ['thread', 'invited_by', 'invited_user']
    readonly_fields = ['created_at', 'responded_at']
    ordering = ['-created_at']


@admin.register(MessageReadReceipt)
class MessageReadReceiptAdmin(admin.ModelAdmin):
    list_display = ['message', 'user', 'read_at']
    raw_id_fields = ['message', 'user']
    readonly_fields = ['read_at']
    ordering = ['-read_at']


@admin.register(MessageDeliveryReceipt)
class MessageDeliveryReceiptAdmin(admin.ModelAdmin):
    list_display = ['message', 'user', 'delivered_at']
    raw_id_fields = ['message', 'user']
    readonly_fields = ['delivered_at']
    ordering = ['-delivered_at']