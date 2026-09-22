# tasks.py
import json
import logging

from celery import shared_task
from pywebpush import webpush, WebPushException
from django.conf import settings

from .models import PushSubscription

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def send_call_push_notifications(self, user_ids, caller_id, caller_name, thread_id):
    subscriptions = PushSubscription.objects.filter(user_id__in=user_ids)

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps({
                    "title": "Incoming Video Call",
                    "body": f"{caller_name} is calling you...",
                    "callerName": caller_name,
                    "callerId": str(caller_id),
                    "threadId": str(thread_id),
                }),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": "mailto:support@learnq.online"},
            )
        except WebPushException as e:
            status_code = getattr(e.response, "status_code", None)
            if status_code in (404, 410):
                # Subscription is gone/expired — clean it up
                sub.delete()
                logger.info("Deleted stale push subscription %s", sub.id)
            else:
                logger.warning("Web push failed for subscription %s: %s", sub.id, e)