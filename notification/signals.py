from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import F
from django.conf import settings

from client.models import Client
from .models import Notification, NotificationPreference, InAppNotificationGroup, DeviceToken



@receiver(post_save, sender=Client)
def create_notification_preference(sender, instance, created, **kwargs):
    if created:
        NotificationPreference.objects.get_or_create(user=instance)


@receiver(post_save, sender=Notification)
def update_notification_group(sender, instance, created, **kwargs):
    if created:
        group, _ = InAppNotificationGroup.objects.get_or_create(
            user=instance.recipient,
            category=instance.category,
            defaults={'count': 0}
        )
        InAppNotificationGroup.objects.filter(pk=group.pk).update(
            count=F('count') + 1,
            last_notification=instance,
            updated_at=timezone.now()
        )


@receiver(post_delete, sender=Notification)
def update_notification_group_on_delete(sender, instance, **kwargs):
    InAppNotificationGroup.objects.filter(
        user=instance.recipient,
        category=instance.category
    ).update(
        count=F('count') - 1,
        updated_at=timezone.now()
    )


@receiver(post_save, sender=Notification)
def update_read_status(sender, instance, **kwargs):
    if instance.status == Notification.Status.READ:
        InAppNotificationGroup.objects.filter(
            user=instance.recipient,
            category=instance.category
        ).update(updated_at=timezone.now())


from django.utils import timezone