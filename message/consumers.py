import json
import logging
from typing import Optional

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import ThreadParticipant, Message, MessageReadReceipt, MessageDeliveryReceipt

User = get_user_model()
logger = logging.getLogger(__name__)


class BaseConsumer(AsyncJsonWebsocketConsumer):
    """Base consumer with common authentication and error handling."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or user.is_anonymous:
            await self.close(code=4401)
            return
        self.user = user
        self.user_id = str(user.id)
        self.user_group = f"user_{self.user_id}"

    async def disconnect(self, close_code):
        pass

    async def send_error(self, code: str, message: str):
        await self.send_json({"type": "error", "code": code, "message": message})

    async def send_success(self, event_type: str, data: dict):
        await self.send_json({"type": event_type, "data": data})


class ThreadConsumer(BaseConsumer):
    """WebSocket consumer for real-time thread messaging."""

    async def connect(self):
        await super().connect()
        if not hasattr(self, 'user'):
            return

        self.thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        self.thread_group = f"thread_{self.thread_id}"

        is_participant = await self.is_participant(self.user, self.thread_id)
        if not is_participant:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.thread_group, self.channel_name)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

        await self.send_success("connected", {
            "thread_id": self.thread_id,
            "user_id": self.user_id
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'thread_group'):
            await self.channel_layer.group_discard(self.thread_group, self.channel_name)
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def receive_json(self, content: dict, **kwargs):
        action = content.get("action")
        if action == "typing":
            await self.handle_typing(content)
        elif action == "read":
            await self.handle_read_receipt(content)
        elif action == "delivery":
            await self.handle_delivery_receipt(content)
        elif action == "ping":
            await self.send_json({"type": "pong", "timestamp": content.get("timestamp")})

    async def handle_typing(self, content: dict):
        is_typing = content.get("is_typing", False)
        await self.channel_layer.group_send(
            self.thread_group,
            {
                "type": "user_typing",
                "user_id": self.user_id,
                "user_name": self.user.display_name,
                "is_typing": is_typing,
            }
        )

    async def handle_read_receipt(self, content: dict):
        message_id = content.get("message_id")
        if message_id:
            await self.mark_as_read(message_id)

    async def handle_delivery_receipt(self, content: dict):
        message_id = content.get("message_id")
        if message_id:
            await self.mark_as_delivered(message_id)

    @database_sync_to_async
    def is_participant(self, user, thread_id):
        return ThreadParticipant.objects.filter(
            thread_id=thread_id, user=user, is_active=True
        ).exists()

    @database_sync_to_async
    def mark_as_read(self, message_id):
        try:
            message = Message.objects.get(id=message_id, thread_id=self.thread_id)
            MessageReadReceipt.objects.get_or_create(message=message, user=self.user)
            ThreadParticipant.objects.filter(
                thread_id=self.thread_id, user=self.user
            ).update(last_read_at=message.created_at)
        except Message.DoesNotExist:
            pass

    @database_sync_to_async
    def mark_as_delivered(self, message_id):
        try:
            message = Message.objects.get(id=message_id, thread_id=self.thread_id)
            MessageDeliveryReceipt.objects.get_or_create(message=message, user=self.user)
            ThreadParticipant.objects.filter(
                thread_id=self.thread_id, user=self.user
            ).update(last_delivered_at=message.created_at)
        except Message.DoesNotExist:
            pass

    async def chat_message(self, event):
        await self.send_json({"type": "message", "data": event["message"]})

    async def user_typing(self, event):
        if event["user_id"] != self.user_id:
            await self.send_json({"type": "typing", "data": event})

    async def message_edited(self, event):
        await self.send_json({"type": "message_edited", "data": event["data"]})

    async def message_deleted(self, event):
        await self.send_json({"type": "message_deleted", "data": event["data"]})

    async def reaction_added(self, event):
        await self.send_json({"type": "reaction_added", "data": event["data"]})

    async def reaction_removed(self, event):
        await self.send_json({"type": "reaction_removed", "data": event["data"]})

    async def user_joined(self, event):
        await self.send_json({"type": "user_joined", "data": event["data"]})

    async def user_left(self, event):
        await self.send_json({"type": "user_left", "data": event["data"]})

    async def thread_updated(self, event):
        await self.send_json({"type": "thread_updated", "data": event["data"]})


class NotificationConsumer(BaseConsumer):
    """WebSocket consumer for global user notifications (unread counts, new threads, etc.)."""

    async def connect(self):
        await super().connect()
        if not hasattr(self, 'user'):
            return

        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

        unread_count = await self.get_unread_count()
        await self.send_success("connected", {
            "user_id": self.user_id,
            "unread_count": unread_count
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def receive_json(self, content: dict, **kwargs):
        action = content.get("action")
        if action == "ping":
            await self.send_json({"type": "pong"})

    @database_sync_to_async
    def get_unread_count(self):
        from .models import Thread
        from django.db.models import Count, Q, OuterRef, Subquery

        last_read_subquery = ThreadParticipant.objects.filter(
            thread=OuterRef('pk'), user=self.user
        ).values('last_read_at')[:1]

        total = Thread.objects.filter(
            participants__user=self.user,
            participants__is_active=True,
            is_active=True
        ).annotate(
            unread=Count(
                'messages',
                filter=Q(messages__created_at__gt=Subquery(last_read_subquery)) & ~Q(messages__sender=self.user)
            )
        ).filter(unread__gt=0).count()

        return total

    async def unread_count_update(self, event):
        await self.send_json({"type": "unread_count", "data": event["data"]})

    async def new_thread(self, event):
        await self.send_json({"type": "new_thread", "data": event["data"]})

    async def thread_updated(self, event):
        await self.send_json({"type": "thread_updated", "data": event["data"]})

    async def call_signal(self, event):
        await self.send_json({"type": "call_signal", "data": event["data"]})