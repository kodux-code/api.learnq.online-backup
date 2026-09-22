from django.db.models.signals import post_save
from django.dispatch import receiver
from client.models import Client
from account.models import StudentAccount, TeacherAccount, ModeratorAccount


@receiver(post_save, sender=Client)
def create_client_account(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.role == Client.Role.STUDENT:
        StudentAccount.objects.get_or_create(client=instance)
    elif instance.role == Client.Role.TEACHER:
        TeacherAccount.objects.get_or_create(client=instance)
    elif instance.role == Client.Role.MODERATOR:
        ModeratorAccount.objects.get_or_create(client=instance)


@receiver(post_save, sender=Client)
def save_client_account(sender, instance, **kwargs):
    if instance.role == Client.Role.STUDENT and hasattr(instance, 'student_account'):
        instance.student_account.save()
    elif instance.role == Client.Role.TEACHER and hasattr(instance, 'teacher_account'):
        instance.teacher_account.save()
    elif instance.role == Client.Role.MODERATOR and hasattr(instance, 'moderator_account'):
        instance.moderator_account.save()