import json
import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.renderers import JSONRenderer

from .models import Message, Thread, ThreadParticipant, ThreadInvite
from .serializers import MessageSerializer

logger = logging.getLogger(__name__)


def _get_channel_layer():
    try:
        return get_channel_layer()
    except Exception:
        return None


def _broadcast_to_thread(thread_id: str, event_type: str, data: dict):
    channel_layer = _get_channel_layer()
    if not channel_layer:
        return

    try:
        async_to_sync(channel_layer.group_send)(
            f"thread_{thread_id}",
            {"type": event_type, "data": data}
        )
    except Exception as e:
        logger.exception("Failed to broadcast %s to thread %s: %s", event_type, thread_id, e)


def _broadcast_to_users(user_ids: list, event_type: str, data: dict):
    channel_layer = _get_channel_layer()
    if not channel_layer:
        return

    for user_id in user_ids:
        try:
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                {"type": event_type, "data": data}
            )
        except Exception as e:
            logger.exception("Failed to notify user %s: %s", user_id, e)


@receiver(post_save, sender=Message)
def broadcast_message(sender, instance, created, **kwargs):
    if not created:
        return

    def _do_broadcast():
        payload = json.loads(JSONRenderer().render(MessageSerializer(instance).data))

        participant_user_ids = list(
            ThreadParticipant.objects.filter(
                thread_id=instance.thread_id, is_active=True
            ).values_list("user_id", flat=True)
        )

        _broadcast_to_thread(
            str(instance.thread_id),
            "chat_message",
            payload
        )

        thread_update = {
            "thread_id": str(instance.thread_id),
            "last_message": {
                "id": str(instance.id),
                "content": instance.display_content if hasattr(instance, 'display_content') else instance.content,
                "message_type": instance.message_type,
                "sender_id": str(instance.sender_id) if instance.sender_id else None,
                "created_at": payload["created_at"],
            },
            "updated_at": payload["created_at"],
        }

        _broadcast_to_users(
            participant_user_ids,
            "thread_updated",
            thread_update
        )

    transaction.on_commit(_do_broadcast)


@receiver(post_save, sender=Message)
def update_thread_last_message(sender, instance, **kwargs):
    """Update thread's denormalized last_message fields."""
    if not getattr(instance, '_updating_thread', False):
        Thread.objects.filter(pk=instance.thread_id).update(
            last_message=instance,
            last_message_at=instance.created_at,
            updated_at=instance.created_at
        )


@receiver(post_save, sender=ThreadInvite)
def broadcast_invite(sender, instance, created, **kwargs):
    if created:
        def _do_broadcast():
            _broadcast_to_users(
                [str(instance.invited_user_id)],
                "new_invite",
                {
                    "invite_id": str(instance.id),
                    "thread_id": str(instance.thread_id),
                    "thread_name": instance.thread.name if instance.thread.thread_type == Thread.ThreadType.GROUP else None,
                    "invited_by": str(instance.invited_by_id),
                    "created_at": instance.created_at.isoformat(),
                }
            )
        transaction.on_commit(_do_broadcast)


@receiver(post_save, sender=ThreadParticipant)
def broadcast_participant_change(sender, instance, created, **kwargs):
    if created:
        def _do_broadcast():
            thread_id = str(instance.thread_id)
            user_ids = list(
                ThreadParticipant.objects.filter(
                    thread_id=thread_id, is_active=True
                ).values_list("user_id", flat=True)
            )

            event_type = "user_joined" if created else "user_left"
            _broadcast_to_users(
                user_ids,
                event_type,
                {
                    "thread_id": thread_id,
                    "user_id": str(instance.user_id),
                    "user_name": instance.user.display_name if instance.user else "Unknown",
                    "role": instance.role,
                }
            )
        transaction.on_commit(_do_broadcast)


@receiver(post_delete, sender=ThreadParticipant)
def broadcast_participant_left(sender, instance, **kwargs):
    def _do_broadcast():
        thread_id = str(instance.thread_id)
        user_ids = list(
            ThreadParticipant.objects.filter(
                thread_id=thread_id, is_active=True
            ).values_list("user_id", flat=True)
        )

        _broadcast_to_users(
            user_ids,
            "user_left",
            {
                "thread_id": thread_id,
                "user_id": str(instance.user_id),
                "user_name": instance.user.display_name if instance.user else "Unknown",
            }
        )
    transaction.on_commit(_do_broadcast)


@receiver(post_save, sender=Thread)
def broadcast_thread_update(sender, instance, created, **kwargs):
    if not created:
        def _do_broadcast():
            user_ids = list(
                ThreadParticipant.objects.filter(
                    thread_id=instance.id, is_active=True
                ).values_list("user_id", flat=True)
            )

            _broadcast_to_users(
                user_ids,
                "thread_updated",
                {
                    "thread_id": str(instance.id),
                    "name": instance.name,
                    "description": instance.description,
                    "allows_reactions": instance.allows_reactions,
                    "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
                }
            )
        transaction.on_commit(_do_broadcast)