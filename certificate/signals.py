import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import F
from django.conf import settings
from django.utils import timezone

from .models import Certificate, CertificateVerification, CertificateBatch, OrganizationProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Certificate)
def create_verification_record(sender, instance, created, **kwargs):
    """Create verification record when certificate is issued."""
    if created and instance.status == Certificate.Status.ISSUED:
        CertificateVerification.objects.get_or_create(
            certificate=instance,
            defaults={
                'student_name': instance.certificate_data.get('student_name', ''),
                'student_email_hash': hash_email(instance.certificate_data.get('student_email', '')),
                'course_title': instance.source_title,
                'issue_date': instance.issue_date,
                'expiry_date': instance.expiry_date,
                'credential_id': instance.credential_id,
                'certificate_number': instance.certificate_number,
                'template_name': instance.template.name if instance.template else '',
            }
        )


@receiver(post_save, sender=Certificate)
def update_verification_on_status_change(sender, instance, **kwargs):
    """Update verification record when certificate status changes."""
    if hasattr(instance, 'verification_record'):
        verification = instance.verification_record
        
        if instance.status == Certificate.Status.REVOKED:
            verification.is_verified = False
            verification.save(update_fields=['is_verified', 'updated_at'])
        
        elif instance.status == Certificate.Status.ISSUED:
            verification.is_verified = True
            verification.save(update_fields=['is_verified', 'updated_at'])


@receiver(post_save, sender=CertificateBatch)
def queue_batch_processing(sender, instance, created, **kwargs):
    """Queue batch for async processing when created."""
    if created and instance.status == CertificateBatch.Status.PENDING:
        from .tasks import process_certificate_batch
        
        try:
            from celery import current_app
            if current_app.conf.task_always_eager or not current_app.conf.broker_url:
                process_certificate_batch(str(instance.id))
            else:
                process_certificate_batch.delay(str(instance.id))
        except ImportError:
            logger.warning("Celery not available, processing batch synchronously")
            process_certificate_batch(str(instance.id))
        except Exception as e:
            logger.exception(f"Failed to queue batch {instance.id}: {e}")


@receiver(post_save, sender=OrganizationProfile)
def ensure_single_organization(sender, instance, **kwargs):
    """Ensure only one organization profile exists."""
    if instance.is_active:
        OrganizationProfile.objects.filter(is_active=True).exclude(pk=instance.pk).update(is_active=False)


def hash_email(email):
    import hashlib
    return hashlib.sha256(email.lower().encode()).hexdigest()