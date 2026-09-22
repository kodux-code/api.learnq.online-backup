from django.db import transaction
from django.db.models import Prefetch, Count, Q, OuterRef, Subquery, Max, F
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import MessageDeliveryReceipt, MessageReadReceipt, Thread, ThreadParticipant, Message, ThreadInvite
from .serializers import (
    ThreadListSerializer, ThreadCreateSerializer, ThreadDetailSerializer,
    ThreadUpdateSerializer, ThreadInviteSerializer, ThreadInviteCreateSerializer,
    ThreadInviteResponseSerializer, MessageSerializer, MessageCreateSerializer,
    MessageEditSerializer, MessageReactionSerializer, UnreadCountSerializer
)
from .permissions import IsThreadParticipant, IsMessageSender, IsThreadAdmin


class StandardPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100


class MessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100
    ordering = '-created_at'


class GlobalUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        last_read_subquery = ThreadParticipant.objects.filter(
            thread=OuterRef('pk'),
            user=user
        ).values('last_read_at')[:1]

        total = Thread.objects.filter(
            participants__user=user,
            participants__is_active=True,
            is_active=True
        ).annotate(
            unread=Count(
                'messages',
                filter=Q(messages__created_at__gt=Subquery(last_read_subquery)) & ~Q(messages__sender=user)
            )
        ).aggregate(total=Count('id', filter=Q(unread__gt=0)))

        return Response({"total_unread": total['total'] or 0}, status=status.HTTP_200_OK)


class ThreadListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ThreadCreateSerializer
        return ThreadListSerializer

    def get_queryset(self):
        user = self.request.user

        last_read_subquery = ThreadParticipant.objects.filter(
            thread=OuterRef('pk'),
            user=user
        ).values('last_read_at')[:1]

        latest_msg_subquery = Message.objects.filter(
            thread=OuterRef('pk')
        ).order_by('-created_at').values('id')[:1]

        return Thread.objects.filter(
            participants__user=user,
            participants__is_active=True,
            is_active=True
        ).select_related('last_message__sender').prefetch_related(
            Prefetch(
                'participants',
                queryset=ThreadParticipant.objects.select_related('user').filter(is_active=True),
                to_attr='active_participants'
            )
        ).annotate(
            unread_count=Count(
                'messages',
                filter=Q(messages__created_at__gt=Subquery(last_read_subquery)) & ~Q(messages__sender=user)
            ),
            participant_count=Count('participants', filter=Q(participants__is_active=True)),
            is_muted=Subquery(
                ThreadParticipant.objects.filter(
                    thread=OuterRef('pk'), user=user
                ).values('is_muted')[:1]
            )
        ).order_by('-last_message_at', '-updated_at')


class ThreadDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]
    serializer_class = ThreadDetailSerializer
    queryset = Thread.objects.filter(is_active=True).prefetch_related(
        Prefetch('participants', queryset=ThreadParticipant.objects.select_related('user').filter(is_active=True))
    )

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return ThreadUpdateSerializer
        return ThreadDetailSerializer

    def perform_update(self, serializer):
        thread = self.get_object()
        if thread.thread_type == Thread.ThreadType.DIRECT:
            raise PermissionDenied("Direct message threads cannot be modified.")

        participant = thread.participants.filter(user=self.request.user).first()
        if participant.role not in [ThreadParticipant.Role.ADMIN, ThreadParticipant.Role.OWNER]:
            raise PermissionDenied("Only admins can update thread details.")

        serializer.save()


class ThreadMarkReadView(APIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]

    def post(self, request, pk):
        thread = self.get_object(pk)
        participant = thread.participants.get(user=request.user, is_active=True)

        last_msg_id = request.data.get('last_message_id')
        if last_msg_id:
            try:
                msg = Message.objects.get(id=last_msg_id, thread=thread)
                participant.last_read_at = msg.created_at
            except Message.DoesNotExist:
                participant.last_read_at = timezone.now()
        else:
            participant.last_read_at = timezone.now()

        participant.save(update_fields=['last_read_at'])

        MessageReadReceipt.objects.bulk_create(
            [
                MessageReadReceipt(message_id=msg_id, user=request.user)
                for msg_id in thread.messages.filter(
                    created_at__lte=participant.last_read_at
                ).exclude(read_receipts__user=request.user).values_list('id', flat=True)
            ],
            ignore_conflicts=True
        )

        return Response({"status": "marked_read", "read_at": participant.last_read_at}, status=status.HTTP_200_OK)

    def get_object(self, pk):
        try:
            return Thread.objects.get(id=pk, is_active=True)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")


class ThreadLeaveView(APIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]

    def post(self, request, pk):
        thread = self.get_object(pk)
        participant = thread.participants.get(user=request.user, is_active=True)

        if thread.thread_type == Thread.ThreadType.GROUP:
            if participant.role == ThreadParticipant.Role.OWNER:
                admins = thread.participants.filter(
                    role__in=[ThreadParticipant.Role.ADMIN, ThreadParticipant.Role.OWNER],
                    is_active=True
                ).exclude(user=request.user)
                if admins.exists():
                    new_owner = admins.first()
                    new_owner.role = ThreadParticipant.Role.OWNER
                    new_owner.save(update_fields=['role'])
                else:
                    thread.is_active = False
                    thread.save(update_fields=['is_active'])
                    return Response({"status": "group_deleted"}, status=status.HTTP_200_OK)

        participant.is_active = False
        participant.save(update_fields=['is_active'])

        Message.objects.create(
            thread=thread,
            sender=None,
            content=_("{user} left the group.").format(user=request.user.display_name),
            message_type=Message.MessageType.SYSTEM,
            is_system_message=True,
            system_event_type='user_left'
        )

        return Response({"status": "left"}, status=status.HTTP_200_OK)

    def get_object(self, pk):
        try:
            return Thread.objects.get(id=pk, is_active=True)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")


class MessageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]
    pagination_class = MessagePagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MessageCreateSerializer
        return MessageSerializer

    def get_queryset(self):
        thread_id = self.kwargs['thread_id']
        user = self.request.user

        if not ThreadParticipant.objects.filter(thread_id=thread_id, user=user, is_active=True).exists():
            raise PermissionDenied("You do not have access to this thread.")

        return Message.objects.filter(
            thread_id=thread_id,
            is_deleted=False
        ).select_related('sender', 'reply_to__sender').prefetch_related(
            'read_receipts', 'delivery_receipts'
        ).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        output_serializer = MessageSerializer(
            serializer.instance,
            context=self.get_serializer_context()
        )
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @transaction.atomic
    def perform_create(self, serializer):
        thread_id = self.kwargs['thread_id']
        user = self.request.user

        thread = Thread.objects.select_for_update().get(id=thread_id, is_active=True)

        if not thread.participants.filter(user=user, is_active=True).exists():
            raise PermissionDenied("You cannot post to this thread.")

        message = serializer.save(sender=user, thread=thread)

        MessageDeliveryReceipt.objects.bulk_create(
            [
                MessageDeliveryReceipt(message=message, user=p.user)
                for p in thread.participants.filter(is_active=True).exclude(user=user)
            ],
            ignore_conflicts=True
        )

        thread.last_message = message
        thread.last_message_at = message.created_at
        thread.save(update_fields=['last_message', 'last_message_at', 'updated_at'])

        ThreadParticipant.objects.filter(thread=thread, is_active=True).exclude(user=user).update(
            last_delivered_at=message.created_at
        )

        if message.reply_to:
            ThreadParticipant.objects.filter(
                thread=thread, user=message.reply_to.sender, is_active=True
            ).update(last_delivered_at=message.created_at)


class MessageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant, IsMessageSender]
    queryset = Message.objects.select_related('sender', 'reply_to__sender', 'thread')

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return MessageEditSerializer
        return MessageSerializer

    def perform_update(self, serializer):
        message = self.get_object()
        message.edit(serializer.validated_data['content'], self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete(self.request.user)


class MessageReactionView(APIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]

    def post(self, request, thread_id, message_id):
        thread = self.get_thread(thread_id)
        try:
            message = Message.objects.get(id=message_id, thread=thread, is_deleted=False)
        except Message.DoesNotExist:
            raise NotFound("Message not found.")

        if not thread.allows_reactions:
            raise PermissionDenied("Reactions are disabled in this thread.")

        serializer = MessageReactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message.add_reaction(request.user, serializer.validated_data['emoji'])

        return Response({
            "reactions": message.reaction_counts,
            "added": serializer.validated_data['emoji']
        }, status=status.HTTP_201_CREATED)

    def delete(self, request, thread_id, message_id):
        thread = self.get_thread(thread_id)
        try:
            message = Message.objects.get(id=message_id, thread=thread, is_deleted=False)
        except Message.DoesNotExist:
            raise NotFound("Message not found.")

        emoji = request.data.get('emoji')
        if not emoji:
            raise ValidationError({"emoji": _("Emoji is required.")})

        message.remove_reaction(request.user, emoji)
        return Response({"reactions": message.reaction_counts, "removed": emoji}, status=status.HTTP_200_OK)

    def get_thread(self, pk):
        try:
            return Thread.objects.get(id=pk, is_active=True)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")


class MessageReadReceiptView(APIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]

    def post(self, request, thread_id, message_id):
        thread = self.get_thread(thread_id)
        try:
            message = Message.objects.get(id=message_id, thread=thread)
        except Message.DoesNotExist:
            raise NotFound("Message not found.")

        receipt, created = MessageReadReceipt.objects.get_or_create(
            message=message, user=request.user
        )

        participant = thread.participants.get(user=request.user, is_active=True)
        if participant.last_read_at < message.created_at:
            participant.last_read_at = message.created_at
            participant.save(update_fields=['last_read_at'])

        return Response({"status": "read", "read_at": receipt.read_at}, status=status.HTTP_201_CREATED)

    def get_thread(self, pk):
        try:
            return Thread.objects.get(id=pk, is_active=True)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")


class ThreadInviteListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsThreadParticipant]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ThreadInviteCreateSerializer
        return ThreadInviteSerializer

    def get_queryset(self):
        thread = self.get_thread(self.kwargs['thread_id'])
        return ThreadInvite.objects.filter(thread=thread, status=ThreadInvite.Status.PENDING)

    def get_thread(self, pk):
        try:
            return Thread.objects.get(id=pk, is_active=True)
        except Thread.DoesNotExist:
            raise NotFound("Thread not found.")


class ThreadInviteResponseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, invite_id):
        try:
            invite = ThreadInvite.objects.select_related('thread').get(
                id=invite_id, invited_user=request.user, status=ThreadInvite.Status.PENDING
            )
        except ThreadInvite.DoesNotExist:
            raise NotFound("Invite not found or already responded.")

        serializer = ThreadInviteResponseSerializer(instance=invite, data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data['action'] == 'accept':
            with transaction.atomic():
                invite.status = ThreadInvite.Status.ACCEPTED
                invite.responded_at = timezone.now()
                invite.save(update_fields=['status', 'responded_at'])

                participant, _ = ThreadParticipant.objects.get_or_create(
                    thread=invite.thread,
                    user=request.user,
                    defaults={'role': ThreadParticipant.Role.MEMBER, 'is_active': True}
                )
                if not participant.is_active:
                    participant.is_active = True
                    participant.save(update_fields=['is_active'])

                Message.objects.create(
                    thread=invite.thread,
                    sender=None,
                    content=_("{user} joined the group.").format(user=request.user.display_name),
                    message_type=Message.MessageType.SYSTEM,
                    is_system_message=True,
                    system_event_type='user_joined'
                )
        else:
            invite.status = ThreadInvite.Status.DECLINED
            invite.responded_at = timezone.now()
            invite.save(update_fields=['status', 'responded_at'])

        return Response(ThreadInviteSerializer(invite).data)


class UserThreadSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, thread_id):
        try:
            participant = ThreadParticipant.objects.get(
                thread_id=thread_id, user=request.user, is_active=True
            )
        except ThreadParticipant.DoesNotExist:
            raise NotFound("Not a participant.")

        return Response({
            'is_muted': participant.is_muted,
            'notifications_enabled': participant.notifications_enabled,
        })

    def patch(self, request, thread_id):
        try:
            participant = ThreadParticipant.objects.get(
                thread_id=thread_id, user=request.user, is_active=True
            )
        except ThreadParticipant.DoesNotExist:
            raise NotFound("Not a participant.")

        if 'is_muted' in request.data:
            participant.is_muted = request.data['is_muted']
        if 'notifications_enabled' in request.data:
            participant.notifications_enabled = request.data['notifications_enabled']
        participant.save(update_fields=['is_muted', 'notifications_enabled'])

        return Response({
            'is_muted': participant.is_muted,
            'notifications_enabled': participant.notifications_enabled,
        })


class UnreadCountDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        last_read_subquery = ThreadParticipant.objects.filter(
            thread=OuterRef('pk'),
            user=user
        ).values('last_read_at')[:1]

        threads = Thread.objects.filter(
            participants__user=user,
            participants__is_active=True,
            is_active=True
        ).annotate(
            unread=Count(
                'messages',
                filter=Q(messages__created_at__gt=Subquery(last_read_subquery)) & ~Q(messages__sender=user)
            )
        ).filter(unread__gt=0).values('id', 'unread')

        return Response({
            "total_unread": sum(t['unread'] for t in threads),
            "by_thread": {str(t['id']): t['unread'] for t in threads}
        })


from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError