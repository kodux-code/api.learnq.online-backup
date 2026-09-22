from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import F
from django.utils import timezone
import uuid
from .models import QuestionBank, Assessment, Attempt, Answer


@receiver(post_save, sender=Answer)
def update_question_usage(sender, instance, created, **kwargs):
    if created:
        QuestionBank.objects.filter(pk=instance.question_id).update(usage_count=F('usage_count') + 1)


@receiver(post_delete, sender=Answer)
def update_question_usage_on_delete(sender, instance, **kwargs):
    QuestionBank.objects.filter(pk=instance.question_id).update(usage_count=F('usage_count') - 1)


@receiver(post_save, sender=Assessment)
def update_assessment_total_points(sender, instance, **kwargs):
    if instance.status == Assessment.Status.PUBLISHED:
        total = sum(
            aq.points_override or aq.question.points
            for aq in instance.assessmentquestion_set.all()
        )
        if instance.total_points != total:
            Assessment.objects.filter(pk=instance.pk).update(total_points=total)


@receiver(post_save, sender=Attempt)
def create_certificate_on_pass(sender, instance, **kwargs):
    """Create certificate when attempt is passed."""
    if instance.is_passed and instance.assessment.certificate_template:
        from certificate.models import Certificate
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Check if certificate already exists
        existing = Certificate.objects.filter(
            student=instance.student,
            source_type=Certificate.SourceType.ASSESSMENT,
            source_id=instance.assessment_id,
            status__in=[Certificate.Status.ISSUED, Certificate.Status.PENDING, Certificate.Status.GENERATING]
        ).first()
        
        if existing:
            return
        
        # Create certificate
        template = instance.assessment.certificate_template
        cert_number = f"CERT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        credential_id = f"CRED-{uuid.uuid4().hex[:12].upper()}"
        
        cert_data = {
            'student_name': instance.student.display_name,
            'student_email': instance.student.email,
            'student_id': str(instance.student.id),
            'course_title': instance.assessment.title,
            'completion_date': instance.submitted_at.isoformat() if instance.submitted_at else timezone.now().isoformat(),
            'issue_date': timezone.now().isoformat(),
            'expiry_date': None,
            'credential_id': credential_id,
            'certificate_number': cert_number,
            'organization_name': 'LearnQ',
            'verification_url': template.verification_url_template.format(credential_id=credential_id),
        }
        
        cert = Certificate.objects.create(
            student=instance.student,
            template=instance.assessment.certificate_template,
            source_type=Certificate.SourceType.ASSESSMENT,
            source_id=instance.assessment_id,
            source_title=instance.assessment.title,
            certificate_number=cert_number,
            credential_id=credential_id,
            status=Certificate.Status.PENDING,
            visibility=Certificate.Visibility.LINK_ONLY,
            completion_date=instance.submitted_at or timezone.now(),
            expiry_date=None,
            certificate_data=cert_data,
            language='en',
            metadata={},
            generated_by=None
        )
        
        # Trigger async PDF generation
        from certificate.tasks import generate_certificate_pdf
        generate_certificate_pdf.delay(str(cert.id))