from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from client.models import Client
from .models import TeacherEarning, PayoutSchedule


@receiver(post_save, sender=Client)
def create_earning_profile(sender, instance, created, **kwargs):
    if created and instance.role == Client.Role.TEACHER:
        TeacherEarning.objects.get_or_create(teacher=instance)
        PayoutSchedule.objects.get_or_create(teacher=instance)