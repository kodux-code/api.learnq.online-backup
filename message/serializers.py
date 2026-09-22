from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from client.serializers import MinimalUserSerializer

from .models import Thread, ThreadParticipant, Message, ThreadInvite

User = get_user_model()


class ThreadParticipantSerializer(serializers.ModelSerializer):
    user = MinimalUserSerializer(read_only=True)
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ThreadParticipant
        fields = ['id', 'user', 'role', 'joined_at', 'last_read_at', 'last_delivered_at', 'is_active', 'is_muted', 'notifications_enabled', 'unread_count']
        read_only_fields = fields

    def get_unread_count(self, obj):
        return obj.get_unread_count()


class MessageSerializer(serializers.ModelSerializer):
    sender = MinimalUserSerializer(read_only=True)
    reply_to = serializers.SerializerMethodField()
    reply_to_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    reactions = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()
    is_delivered = serializers.SerializerMethodField()
    display_content = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'thread', 'sender', 'reply_to', 'reply_to_id',
            'message_type', 'content', 'display_content', 'metadata',
            'media_url', 'media_thumbnail', 'media_name', 'media_size',
            'media_duration', 'media_mime_type',
            'is_edited', 'edited_at', 'is_deleted', 'deleted_at',
            'is_system_message', 'system_event_type',
            'reactions', 'reaction_counts', 'is_read', 'is_delivered',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'thread', 'sender', 'reply_to', 'is_edited', 'edited_at',
            'is_deleted', 'deleted_at', 'is_system_message', 'system_event_type',
            'reaction_counts', 'created_at', 'updated_at'
        ]

    def get_reply_to(self, obj):
        if obj.reply_to:
            return {
                'id': obj.reply_to.id,
                'sender': MinimalUserSerializer(obj.reply_to.sender).data if obj.reply_to.sender else None,
                'content': obj.reply_to.display_content if not obj.reply_to.is_deleted else _("This message was deleted."),
                'message_type': obj.reply_to.message_type,
                'created_at': obj.reply_to.created_at,
            }
        return None

    def get_reactions(self, obj):
        return obj.reaction_counts or {}

    def get_is_read(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.read_receipts.filter(user=request.user).exists()

    def get_is_delivered(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.delivery_receipts.filter(user=request.user).exists()

    def get_display_content(self, obj):
        if obj.is_deleted:
            return _("This message was deleted.")
        if obj.is_system_message:
            return obj.content
        return obj.content

    def validate_reply_to_id(self, value):
        if value:
            try:
                reply_msg = Message.objects.select_related('thread').get(id=value)
                thread_id = self.context.get('thread_id')
                if thread_id and str(reply_msg.thread_id) != str(thread_id):
                    raise ValidationError(_("Reply target must be in the same thread."))
            except Message.DoesNotExist:
                raise ValidationError(_("The message you are replying to does not exist."))
        return value


class MessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['message_type', 'content', 'metadata', 'reply_to',
                  'media_url', 'media_thumbnail', 'media_name', 'media_size',
                  'media_duration', 'media_mime_type']

    def validate(self, attrs):
        message_type = attrs.get('message_type', Message.MessageType.TEXT)
        content = attrs.get('content', '').strip()

        if message_type == Message.MessageType.TEXT and not content:
            raise ValidationError({"content": _("Text messages cannot be empty.")})
        
        if message_type in [Message.MessageType.IMAGE, Message.MessageType.FILE, 
                           Message.MessageType.AUDIO, Message.MessageType.VIDEO]:
            if not attrs.get('media_url'):
                raise ValidationError({"media_url": _("Media URL is required for media messages.")})
        
        return attrs


class MessageEditSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=10000)

    def validate_content(self, value):
        if not value.strip():
            raise ValidationError(_("Message content cannot be empty."))
        return value.strip()


class MessageReactionSerializer(serializers.Serializer):
    emoji = serializers.CharField(max_length=10)

    def validate_emoji(self, value):
        if not value:
            raise ValidationError(_("Emoji is required."))
        return value


class ThreadListSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True)
    last_message = serializers.SerializerMethodField()
    participant_count = serializers.IntegerField(read_only=True)
    is_muted = serializers.BooleanField(read_only=True)

    class Meta:
        model = Thread
        fields = [
            'id', 'thread_type', 'display_name', 'avatar', 'description',
            'unread_count', 'last_message', 'last_message_at',
            'participant_count', 'is_muted', 'is_active',
            'created_at', 'updated_at'
        ]

    def get_display_name(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_name(request.user)
        return obj.name or _("Direct Chat")

    def get_avatar(self, obj):
        if obj.thread_type == Thread.ThreadType.GROUP:
            return None
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            participant = obj.participants.filter(is_active=True).exclude(user=request.user).first()
            if participant and participant.user:
                return MinimalUserSerializer(participant.user).data.get('avatar')
        return None

    def get_last_message(self, obj):
        if obj.last_message:
            return {
                'id': obj.last_message.id,
                'content': obj.last_message.display_content,
                'message_type': obj.last_message.message_type,
                'sender_id': str(obj.last_message.sender_id) if obj.last_message.sender_id else None,
                'created_at': obj.last_message.created_at,
                'is_read': self._check_read(obj.last_message),
            }
        return None

    def _check_read(self, message):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return message.read_receipts.filter(user=request.user).exists()
        return False


class ThreadCreateSerializer(serializers.ModelSerializer):
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=True,
        min_length=1,
        max_length=100,
        help_text=_("List of UUIDs for users to include in the thread.")
    )

    class Meta:
        model = Thread
        fields = ['id', 'thread_type', 'name', 'description', 'participant_ids']

    def validate(self, attrs):
        thread_type = attrs.get('thread_type')
        name = attrs.get('name', '').strip()
        participant_ids = set(attrs.get('participant_ids', []))

        request = self.context.get('request')
        current_user_id = request.user.id
        participant_ids.discard(current_user_id)

        if not participant_ids:
            raise ValidationError({"participant_ids": _("You must specify at least one other participant.")})

        if thread_type == Thread.ThreadType.DIRECT:
            if len(participant_ids) != 1:
                raise ValidationError({"participant_ids": _("Direct messages must have exactly one other participant.")})
            if name:
                raise ValidationError({"name": _("Direct messages cannot have a custom name.")})

        elif thread_type == Thread.ThreadType.GROUP:
            if not name:
                raise ValidationError({"name": _("Group chats require a name.")})
            if len(participant_ids) > 99:
                raise ValidationError({"participant_ids": _("Group cannot exceed 100 participants.")})

        valid_users = User.objects.filter(id__in=participant_ids, is_active=True)
        if valid_users.count() != len(participant_ids):
            invalid = participant_ids - set(valid_users.values_list('id', flat=True))
            raise ValidationError({"participant_ids": _(f"Invalid or inactive user IDs: {invalid}")})

        attrs['cleaned_participant_ids'] = list(participant_ids)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        thread_type = validated_data['thread_type']
        name = validated_data.get('name', '')
        description = validated_data.get('description', '')
        other_participant_ids = validated_data.pop('cleaned_participant_ids')
        request_user = self.context['request'].user

        if thread_type == Thread.ThreadType.DIRECT:
            target_user_id = other_participant_ids[0]
            existing = Thread.objects.filter(
                thread_type=Thread.ThreadType.DIRECT,
                participants__user_id=request_user.id
            ).filter(
                participants__user_id=target_user_id
            ).first()
            if existing:
                return existing

        thread = Thread.objects.create(
            thread_type=thread_type,
            name=name,
            description=description,
        )

        participants = [
            ThreadParticipant(
                thread=thread,
                user_id=request_user.id,
                role=ThreadParticipant.Role.OWNER if thread_type == Thread.ThreadType.GROUP else ThreadParticipant.Role.MEMBER
            )
        ]
        for user_id in other_participant_ids:
            participants.append(ThreadParticipant(
                thread=thread,
                user_id=user_id,
                role=ThreadParticipant.Role.MEMBER
            ))
        ThreadParticipant.objects.bulk_create(participants)

        if thread_type == Thread.ThreadType.GROUP:
            Message.objects.create(
                thread=thread,
                sender=None,
                content=_("Group '{name}' created by {creator}.").format(name=name, creator=request_user.display_name),
                message_type=Message.MessageType.SYSTEM,
                is_system_message=True,
                system_event_type='group_created'
            )

        return thread


class ThreadDetailSerializer(serializers.ModelSerializer):
    participants = ThreadParticipantSerializer(many=True, read_only=True)
    display_name = serializers.SerializerMethodField()
    current_user_role = serializers.SerializerMethodField()

    class Meta:
        model = Thread
        fields = ['id', 'thread_type', 'display_name', 'name', 'description',
                  'allows_reactions', 'participants', 'current_user_role',
                  'created_at', 'updated_at', 'is_active']

    def get_display_name(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_name(request.user)
        return obj.name or _("Direct Chat")

    def get_current_user_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            participant = obj.participants.filter(user=request.user, is_active=True).first()
            return participant.role if participant else None
        return None


class ThreadUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Thread
        fields = ['name', 'description', 'allows_reactions']

    def validate(self, attrs):
        instance = self.instance
        if instance.thread_type == Thread.ThreadType.DIRECT:
            raise ValidationError(_("Direct message threads cannot be modified."))
        return attrs


class ThreadInviteSerializer(serializers.ModelSerializer):
    invited_by = MinimalUserSerializer(read_only=True)
    invited_user = MinimalUserSerializer(read_only=True)
    thread = ThreadListSerializer(read_only=True)

    class Meta:
        model = ThreadInvite
        fields = ['id', 'thread', 'invited_by', 'invited_user', 'status', 'created_at', 'responded_at']
        read_only_fields = fields


class ThreadInviteCreateSerializer(serializers.ModelSerializer):
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=True
    )

    class Meta:
        model = ThreadInvite
        fields = ['thread', 'user_ids']

    def validate(self, attrs):
        thread = attrs['thread']
        user_ids = set(attrs['user_ids'])
        request_user = self.context['request'].user

        if thread.thread_type != Thread.ThreadType.GROUP:
            raise ValidationError({"thread": _("Can only invite to group threads.")})

        participant = thread.participants.filter(user=request_user, is_active=True).first()
        if not participant or participant.role not in [ThreadParticipant.Role.ADMIN, ThreadParticipant.Role.OWNER]:
            raise ValidationError({"thread": _("Only admins can invite users.")})

        user_ids.discard(request_user.id)
        existing = thread.participants.filter(user_id__in=user_ids, is_active=True).values_list('user_id', flat=True)
        if existing:
            raise ValidationError({"user_ids": _(f"Users already in thread: {list(existing)}")})

        pending = ThreadInvite.objects.filter(
            thread=thread, invited_user_id__in=user_ids, status=ThreadInvite.Status.PENDING
        ).values_list('invited_user_id', flat=True)
        if pending:
            raise ValidationError({"user_ids": _(f"Invites already pending for: {list(pending)}")})

        valid_users = User.objects.filter(id__in=user_ids, is_active=True)
        if valid_users.count() != len(user_ids):
            invalid = user_ids - set(valid_users.values_list('id', flat=True))
            raise ValidationError({"user_ids": _(f"Invalid user IDs: {invalid}")})

        attrs['cleaned_user_ids'] = list(user_ids)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        thread = validated_data['thread']
        user_ids = validated_data.pop('cleaned_user_ids')
        request_user = self.context['request'].user

        invites = []
        for user_id in user_ids:
            invite, _ = ThreadInvite.objects.get_or_create(
                thread=thread,
                invited_user_id=user_id,
                defaults={'invited_by': request_user, 'status': ThreadInvite.Status.PENDING}
            )
            invites.append(invite)

        return invites[0] if invites else None


class ThreadInviteResponseSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['accept', 'decline'])

    def validate(self, attrs):
        invite = self.instance
        if invite.status != ThreadInvite.Status.PENDING:
            raise ValidationError(_("Invite has already been responded to."))
        if invite.invited_user != self.context['request'].user:
            raise ValidationError(_("Not your invite."))
        return attrs


class UnreadCountSerializer(serializers.Serializer):
    total_unread = serializers.IntegerField()
    by_thread = serializers.DictField(child=serializers.IntegerField())