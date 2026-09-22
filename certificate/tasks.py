from celery import shared_task
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings
import hashlib
import uuid
import logging

from certificate.models import CertificateBatch, CertificateTemplate

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_certificate_batch(self, batch_id: str):
    """
    Celery task to process a certificate batch asynchronously.
    """
    from certificate.models import (
        Certificate, CertificateBatch, CertificateTemplate, 
        CertificateVerification, CertificateShare
    )
    from course.models import Enrollment, Course
    from assessment.models import Attempt
    
    User = get_user_model()
    
    try:
        batch = CertificateBatch.objects.select_related('template', 'created_by').get(id=batch_id)
    except CertificateBatch.DoesNotExist:
        logger.error(f"Batch {batch_id} not found")
        return {"status": "error", "message": "Batch not found"}
    
    if batch.status not in [CertificateBatch.Status.PENDING, CertificateBatch.Status.FAILED]:
        logger.warning(f"Batch {batch_id} not in pending/failed state: {batch.status}")
        return {"status": "error", "message": f"Invalid state: {batch.status}"}
    
    batch.status = CertificateBatch.Status.PROCESSING
    batch.started_at = timezone.now()
    batch.save(update_fields=['status', 'started_at', 'updated_at'])
    
    try:
        recipients = _find_recipients(batch)
        batch.total_recipients = len(recipients)
        batch.save(update_fields=['total_recipients', 'updated_at'])
        
        template = batch.template
        
        for student in recipients:
            try:
                _process_single_certificate(batch, template, student)
                batch.success_count += 1
            except Exception as e:
                batch.failed_count += 1
                batch.error_log += f"\n{student.id}: {str(e)}"
                logger.exception(f"Failed to create certificate for student {student.id} in batch {batch_id}")
            
            batch.processed_count += 1
            batch.save(update_fields=['processed_count', 'success_count', 'failed_count', 'error_log', 'updated_at'])
        
        batch.status = CertificateBatch.Status.COMPLETED if batch.failed_count == 0 else CertificateBatch.Status.PARTIAL
        
    except Exception as e:
        batch.status = CertificateBatch.Status.FAILED
        batch.error_log = str(e)
        logger.exception(f"Batch {batch_id} failed")
        raise self.retry(exc=e)
    finally:
        batch.completed_at = timezone.now()
        batch.save(update_fields=['status', 'completed_at', 'error_log', 'updated_at'])
    
    return {
        "status": batch.status,
        "processed": batch.processed_count,
        "success": batch.success_count,
        "failed": batch.failed_count
    }


def _find_recipients(batch: CertificateBatch):
    """Find eligible recipients based on batch filters."""
    from course.models import Enrollment, Program
    from assessment.models import Attempt
    from certificate.models import Certificate
    
    User = get_user_model()
    filter_data = batch.recipient_filter or {}
    recipients = []
    
    if filter_data.get('course_id'):
        course_id = filter_data['course_id']
        source_type = batch.source_type
        
        if source_type == Certificate.SourceType.COURSE:
            enrollments = Enrollment.objects.filter(
                course_id=course_id,
                status=Enrollment.Status.COMPLETED
            ).select_related('student')
            recipients = [e.student for e in enrollments if e.student.is_active]
        
        elif source_type == Certificate.SourceType.ASSESSMENT:
            attempts = Attempt.objects.filter(
                assessment__course_id=course_id,
                is_passed=True
            ).select_related('student')
            seen = set()
            for a in attempts:
                if a.student.is_active and a.student_id not in seen:
                    recipients.append(a.student)
                    seen.add(a.student_id)
        
        elif source_type == Certificate.SourceType.PROGRAM:
            try:
                program = Program.objects.get(id=course_id)
                course_ids = program.courses.values_list('id', flat=True)
                student_ids = Enrollment.objects.filter(
                    course_id__in=course_ids,
                    status=Enrollment.Status.COMPLETED
                ).values('student_id').annotate(cnt=models.Count('id')).filter(cnt=len(course_ids))
                recipients = User.objects.filter(id__in=[s['student_id'] for s in student_ids], is_active=True)
            except Program.DoesNotExist:
                pass
    
    elif filter_data.get('student_ids'):
        recipients = list(User.objects.filter(id__in=filter_data['student_ids'], is_active=True))
    
    elif filter_data.get('assessment_id'):
        attempts = Attempt.objects.filter(
            assessment_id=filter_data['assessment_id'],
            is_passed=True
        ).select_related('student')
        seen = set()
        for a in attempts:
            if a.student.is_active and a.student_id not in seen:
                recipients.append(a.student)
                seen.add(a.student_id)
    
    return recipients


def _process_single_certificate(batch: CertificateBatch, template: CertificateTemplate, student):
    """Create a single certificate for a student."""
    from certificate.models import Certificate, CertificateVerification, CertificateShare
    
    User = get_user_model()
    
    # Check if already exists
    existing = Certificate.objects.filter(
        student=student,
        source_type=batch.source_type,
        source_id=batch.source_id,
        status__in=[Certificate.Status.ISSUED, Certificate.Status.PENDING, Certificate.Status.GENERATING]
    ).first()
    
    if existing:
        raise ValueError(f"Certificate already exists for student {student.id}")
    
    cert_number = f"CERT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    credential_id = f"CRED-{uuid.uuid4().hex[:12].upper()}"
    
    custom_data = batch.custom_data or {}
    cert_data = {
        'student_name': student.display_name,
        'student_email': student.email,
        'student_id': str(student.id),
        'course_title': custom_data.get('source_title', 'Course Completion'),
        'completion_date': batch.issue_date.isoformat(),
        'issue_date': timezone.now().isoformat(),
        'expiry_date': batch.expiry_date.isoformat() if batch.expiry_date else None,
        'credential_id': credential_id,
        'certificate_number': cert_number,
        'organization_name': custom_data.get('organization_name', 'LearnQ'),
        'verification_url': template.verification_url_template.format(credential_id=credential_id),
        **custom_data
    }
    
    cert = Certificate.objects.create(
        student=student,
        template=template,
        source_type=batch.source_type,
        source_id=batch.source_id,
        source_title=custom_data.get('source_title', 'Course Completion'),
        certificate_number=cert_number,
        credential_id=credential_id,
        status=Certificate.Status.ISSUED,
        visibility=Certificate.Visibility.LINK_ONLY,
        completion_date=batch.issue_date,
        expiry_date=batch.expiry_date,
        certificate_data=cert_data,
        language='en',
        metadata=custom_data,
        generated_by=batch.created_by
    )
    
    # Create verification record
    CertificateVerification.objects.create(
        certificate=cert,
        student_name=student.display_name,
        student_email_hash=hashlib.sha256(student.email.lower().encode()).hexdigest(),
        course_title=custom_data.get('source_title', 'Course Completion'),
        issue_date=batch.issue_date,
        expiry_date=batch.expiry_date,
        credential_id=credential_id,
        certificate_number=cert_number,
        template_name=template.name,
    )
    
    # Track initial share
    CertificateShare.objects.get_or_create(
        certificate=cert,
        user=student,
        share_type=CertificateShare.ShareType.DOWNLOAD,
        defaults={'ip_address': None, 'user_agent': 'auto_batch_issue'}
    )


@shared_task
def generate_certificate_pdf(certificate_id: str):
    """
    Generate PDF for a certificate using WeasyPrint.
    """
    from certificate.models import Certificate
    
    try:
        cert = Certificate.objects.select_related('template', 'student').get(id=certificate_id)
    except Certificate.DoesNotExist:
        logger.error(f"Certificate {certificate_id} not found")
        return {"status": "error", "message": "Certificate not found"}
    
    cert.status = Certificate.Status.GENERATING
    cert.generated_at = timezone.now()
    cert.save(update_fields=['status', 'generated_at', 'updated_at'])
    
    try:
        from weasyprint import HTML, CSS
        from django.template.loader import render_to_string
        from django.core.files.base import ContentFile
        
        html = render_to_string('certificate/pdf.html', {
            'certificate': cert,
            'data': cert.certificate_data,
            'template': cert.template,
        })
        
        css_string = cert.template.css_styles or ''
        if cert.template.font_family:
            css_string += f"\nbody {{ font-family: {cert.template.font_family}; }}"
        if cert.template.heading_font:
            css_string += f"\nh1, h2, h3 {{ font-family: {cert.template.heading_font}; }}"
        
        pdf_bytes = HTML(string=html, base_url=settings.WEASYPRINT_BASE_URL).write_pdf(
            stylesheets=[CSS(string=css_string)] if css_string else [],
            presentational_hints=True
        )
        
        filename = f"{cert.certificate_number}.pdf"
        cert.pdf_file.save(filename, ContentFile(pdf_bytes))
        cert.pdf_size = len(pdf_bytes)
        cert.status = Certificate.Status.ISSUED
        cert.generation_error = ''
        cert.save(update_fields=['pdf_file', 'pdf_size', 'status', 'generation_error', 'updated_at'])
        
        return {"status": "success", "pdf_size": len(pdf_bytes)}
        
    except ImportError:
        cert.status = Certificate.Status.FAILED
        cert.generation_error = "WeasyPrint not installed. Install with: pip install weasyprint"
        cert.save(update_fields=['status', 'generation_error', 'updated_at'])
        logger.error("WeasyPrint not installed")
        return {"status": "error", "message": "WeasyPrint not installed"}
        
    except Exception as e:
        cert.status = Certificate.Status.FAILED
        cert.generation_error = str(e)
        cert.save(update_fields=['status', 'generation_error', 'updated_at'])
        logger.exception(f"PDF generation failed for {certificate_id}")
        return {"status": "error", "message": str(e)}


@shared_task
def regenerate_certificate_pdf(certificate_id: str):
    """Regenerate PDF for an existing certificate."""
    from certificate.models import Certificate
    
    try:
        cert = Certificate.objects.get(id=certificate_id)
    except Certificate.DoesNotExist:
        return {"status": "error", "message": "Certificate not found"}
    
    if cert.pdf_file:
        cert.pdf_file.delete(save=False)
    
    return generate_certificate_pdf(certificate_id)


@shared_task
def cleanup_expired_certificates():
    """Daily task to mark expired certificates."""
    from certificate.models import Certificate
    
    now = timezone.now()
    expired = Certificate.objects.filter(
        status=Certificate.Status.ISSUED,
        expiry_date__lt=now
    )
    
    count = expired.update(status=Certificate.Status.EXPIRED)
    
    for cert in expired:
        if hasattr(cert, 'verification_record'):
            cert.verification_record.is_verified = False
            cert.verification_record.save(update_fields=['is_verified'])
    
    logger.info(f"Marked {count} certificates as expired")
    return {"expired_count": count}


@shared_task
def sync_blockchain_verification(certificate_id: str):
    """Sync certificate verification to blockchain."""
    from certificate.models import Certificate, OrganizationProfile
    
    try:
        cert = Certificate.objects.select_related('template').get(id=certificate_id)
        org = OrganizationProfile.objects.filter(is_active=True, blockchain_enabled=True).first()
    except (Certificate.DoesNotExist, OrganizationProfile.DoesNotExist):
        return {"status": "error", "message": "Certificate or organization not configured"}
    
    if not org or not org.blockchain_enabled:
        return {"status": "skipped", "message": "Blockchain not enabled"}
    
    return {"status": "not_implemented", "message": "Blockchain integration placeholder"}