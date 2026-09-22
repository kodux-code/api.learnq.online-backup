import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


User = settings.AUTH_USER_MODEL


class ThreadManager(models.Manager):
    def get_user_threads(self, user):
        return self.filter(
            participants__user=user,
            participants__is_active=True,
            is_active=True
        ).select_related('last_message__sender').prefetch_related(
            models.Prefetch(
                'participants',
                queryset=ThreadParticipant.objects.select_related('user').filter(is_active=True)
            )
        ).annotate(
            unread_count=models.Count(
                'messages',
                filter=models.Q(messages__created_at__gt=models.F('participants__last_read_at')) & ~models.Q(messages__sender=user)
            )
        ).order_by('-updated_at')


class ThreadParticipant(models.Model):
    class Role(models.TextChoices):
        MEMBER = 'member', _('Member')
        ADMIN = 'admin', _('Admin')
        OWNER = 'owner', _('Owner')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey('message.Thread', on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='thread_memberships')
    
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    
    # State tracking
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Timestamp of last read message. Used to calculate unread counts.")
    )
    last_delivered_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Timestamp of last delivered message for delivery receipts.")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("False if the user has left the group or blocked the direct thread.")
    )
    is_muted = models.BooleanField(default=False)
    notifications_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Thread Participant")
        verbose_name_plural = _("Thread Participants")
        constraints = [
            models.UniqueConstraint(fields=['thread', 'user'], name='unique_thread_participant')
        ]
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['thread', 'is_active', 'role']),
        ]

    def __str__(self):
        return f"{self.user} in {self.thread_id} ({self.role})"

    def mark_as_read(self, message_id=None):
        if message_id:
            try:
                msg = Message.objects.get(id=message_id, thread=self.thread)
                self.last_read_at = msg.created_at
            except Message.DoesNotExist:
                self.last_read_at = timezone.now()
        else:
            self.last_read_at = timezone.now()
        self.save(update_fields=['last_read_at'])

    def mark_as_delivered(self, message_id=None):
        if message_id:
            try:
                msg = Message.objects.get(id=message_id, thread=self.thread)
                self.last_delivered_at = msg.created_at
            except Message.DoesNotExist:
                self.last_delivered_at = timezone.now()
        else:
            self.last_delivered_at = timezone.now()
        self.save(update_fields=['last_delivered_at'])

    def get_unread_count(self):
        return self.thread.messages.filter(
            created_at__gt=self.last_read_at
        ).exclude(sender=self.user).count()


class Thread(models.Model):
    class ThreadType(models.TextChoices):
        DIRECT = 'direct', _('Direct Message')
        GROUP = 'group', _('Group Message')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread_type = models.CharField(
        max_length=10,
        choices=ThreadType.choices,
        db_index=True
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text=_("Optional group name. Leave blank for DIRECT threads.")
    )
    description = models.TextField(blank=True, default='')
    
    # Denormalized last message for efficient inbox queries
    last_message = models.ForeignKey(
        'Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text=_("Denormalized latest message for inbox preview")
    )
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Settings
    is_muted = models.BooleanField(default=False)
    allows_reactions = models.BooleanField(default=True)
    
    # Audit & Lifecycle
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True,
        help_text=_("Soft delete for the entire thread")
    )

    objects = ThreadManager()

    class Meta:
        verbose_name = _("Thread")
        verbose_name_plural = _("Threads")
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['thread_type', 'is_active']),
            models.Index(fields=['last_message_at']),
        ]

    def __str__(self):
        if self.thread_type == self.ThreadType.GROUP and self.name:
            return f"Group: {self.name}"
        return f"{self.thread_type} Thread {self.id}"

    def get_display_name(self, user):
        if self.thread_type == self.ThreadType.GROUP:
            return self.name or _("Unnamed Group")
        
        participant = self.participants.filter(is_active=True).exclude(user=user).first()
        return participant.user.display_name if participant and participant.user else _("Deleted User")

    def get_other_participants(self, user):
        return self.participants.filter(is_active=True).exclude(user=user).select_related('user')

    def can_user_access(self, user):
        return self.participants.filter(user=user, is_active=True).exists()

    def add_participant(self, user, role=ThreadParticipant.Role.MEMBER):
        return ThreadParticipant.objects.get_or_create(
            thread=self,
            user=user,
            defaults={'role': role, 'is_active': True}
        )

    def remove_participant(self, user):
        ThreadParticipant.objects.filter(thread=self, user=user).update(is_active=False)


class Message(models.Model):
    class MessageType(models.TextChoices):
        TEXT = 'text', _('Text')
        IMAGE = 'image', _('Image')
        FILE = 'file', _('File')
        AUDIO = 'audio', _('Audio')
        VIDEO = 'video', _('Video')
        LOCATION = 'location', _('Location')
        CONTACT = 'contact', _('Contact')
        SYSTEM = 'system', _('System')
        CALL_LOG = 'call_log', _('Call Log')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages',
        help_text=_("SET_NULL preserves messages if user is deleted.")
    )
    
    # Threaded replies
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies'
    )
    
    # Content
    message_type = models.CharField(max_length=15, choices=MessageType.choices, default=MessageType.TEXT)
    content = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    
    # Media fields (for non-text types)
    media_url = models.URLField(blank=True, default='')
    media_thumbnail = models.URLField(blank=True, default='')
    media_name = models.CharField(max_length=255, blank=True, default='')
    media_size = models.PositiveIntegerField(default=0)
    media_duration = models.PositiveIntegerField(default=0)  # seconds for audio/video
    media_mime_type = models.CharField(max_length=100, blank=True, default='')
    
    # Status
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    
    # Soft deletion
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_messages'
    )
    
    # System messages
    is_system_message = models.BooleanField(default=False)
    system_event_type = models.CharField(max_length=50, blank=True, default='')
    
    # Reactions (denormalized count)
    reaction_counts = models.JSONField(default=dict, blank=True)
    
    # Delivery/Read tracking
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['thread', 'created_at']),
            models.Index(fields=['thread', 'sender', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['reply_to', 'created_at']),
        ]

    def __str__(self):
        preview = self.content[:50] if self.content else f"[{self.get_message_type_display()}]"
        return f"Msg {self.id} in {self.thread_id}: {preview}"

    def soft_delete(self, user):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.content = ""
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'content', 'updated_at'])

    def edit(self, new_content, user):
        if self.sender != user:
            raise PermissionError("Only sender can edit message")
        self.content = new_content
        self.is_edited = True
        self.edited_at = timezone.now()
        self.save(update_fields=['content', 'is_edited', 'edited_at', 'updated_at'])

    def add_reaction(self, user, emoji):
        counts = self.reaction_counts or {}
        counts[emoji] = counts.get(emoji, 0) + 1
        self.reaction_counts = counts
        self.save(update_fields=['reaction_counts', 'updated_at'])

    def remove_reaction(self, user, emoji):
        counts = self.reaction_counts or {}
        if emoji in counts:
            counts[emoji] -= 1
            if counts[emoji] <= 0:
                del counts[emoji]
        self.reaction_counts = counts
        self.save(update_fields=['reaction_counts', 'updated_at'])


class MessageReadReceipt(models.Model):
    """Tracks per-user read status for messages in group chats."""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_receipts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_read_receipts')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')
        indexes = [
            models.Index(fields=['user', 'read_at']),
        ]

    def __str__(self):
        return f"{self.user} read {self.message_id} at {self.read_at}"


class MessageDeliveryReceipt(models.Model):
    """Tracks per-user delivery status for messages."""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='delivery_receipts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_delivery_receipts')
    delivered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')
        indexes = [
            models.Index(fields=['user', 'delivered_at']),
        ]

    def __str__(self):
        return f"{self.user} received {self.message_id} at {self.delivered_at}"


class ThreadInvite(models.Model):
    """For inviting users to group threads."""
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        DECLINED = 'declined', _('Declined')
        EXPIRED = 'expired', _('Expired')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='invites')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invites')
    invited_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invites')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('thread', 'invited_user', 'status')
        indexes = [
            models.Index(fields=['invited_user', 'status']),
        ]

    def __str__(self):
        return f"Invite to {self.thread} for {self.invited_user} ({self.status})"


from django.utils import timezone