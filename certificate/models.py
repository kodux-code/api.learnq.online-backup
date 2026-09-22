from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid

User = settings.AUTH_USER_MODEL


class CertificateStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Generation'
    GENERATING = 'generating', 'Generating PDF'
    ISSUED = 'issued', 'Issued'
    REVOKED = 'revoked', 'Revoked'
    EXPIRED = 'expired', 'Expired'
    FAILED = 'failed', 'Generation Failed'


class CertificateVisibility(models.TextChoices):
    PRIVATE = 'private', 'Private'
    PUBLIC = 'public', 'Public (Verifiable)'
    LINK_ONLY = 'link_only', 'Link Only'


class CertificateTemplate(models.Model):
    """Advanced certificate templates with dynamic fields."""
    
    class Orientation(models.TextChoices):
        LANDSCAPE = 'landscape', 'Landscape'
        PORTRAIT = 'portrait', 'Portrait'
    
    class Format(models.TextChoices):
        PDF = 'pdf', 'PDF'
        PNG = 'png', 'PNG'
        SVG = 'svg', 'SVG'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    
    # Template content
    html_template = models.TextField(
        help_text="Jinja2 template with placeholders like {{student_name}}, {{course_title}}, {{completion_date}}"
    )
    css_styles = models.TextField(blank=True)
    
    # Layout
    orientation = models.CharField(max_length=20, choices=Orientation.choices, default=Orientation.LANDSCAPE)
    page_width = models.FloatField(default=1123, validators=[MinValueValidator(100)])  # px at 96 DPI
    page_height = models.FloatField(default=794, validators=[MinValueValidator(100)])
    margin_top = models.FloatField(default=50)
    margin_right = models.FloatField(default=50)
    margin_bottom = models.FloatField(default=50)
    margin_left = models.FloatField(default=50)
    
    # Assets
    background_image = models.ImageField(upload_to='certificates/templates/', null=True, blank=True)
    logo_image = models.ImageField(upload_to='certificates/logos/', null=True, blank=True)
    seal_image = models.ImageField(upload_to='certificates/seals/', null=True, blank=True)
    
    # Fonts
    font_family = models.CharField(max_length=100, default='Georgia, serif')
    heading_font = models.CharField(max_length=100, default='Playfair Display, serif')
    
    # Output
    output_format = models.CharField(max_length=10, choices=Format.choices, default=Format.PDF)
    dpi = models.IntegerField(default=300, validators=[MinValueValidator(72), MaxValueValidator(600)])
    
    # QR/Verification
    include_qr_code = models.BooleanField(default=True)
    qr_code_size = models.FloatField(default=80)
    verification_url_template = models.CharField(
        max_length=500,
        default='https://verify.example.com/cert/{credential_id}',
        help_text="Use {credential_id} placeholder"
    )
    
    # Metadata
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_templates')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', 'name']
        indexes = [
            models.Index(fields=['slug', 'is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def get_available_variables(self):
        """Return all available template variables."""
        base_vars = [
            'student_name', 'student_email', 'student_id',
            'course_title', 'course_slug', 'course_description',
            'completion_date', 'issue_date', 'expiry_date',
            'credential_id', 'certificate_id', 'verification_url',
            'instructor_name', 'instructor_title', 'organization_name',
            'duration_hours', 'grade', 'score_percentage',
            'certificate_number', 'qr_code_data_uri',
        ]
        return base_vars


class Certificate(models.Model):
    """Issued certificates with full verification chain."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core references
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    template = models.ForeignKey(CertificateTemplate, on_delete=models.PROTECT, related_name='certificates')
    
    # Source (what earned this certificate)
    class SourceType(models.TextChoices):
        COURSE = 'course', 'Course Completion'
        ASSESSMENT = 'assessment', 'Assessment Passed'
        PROGRAM = 'program', 'Program Completion'
        CUSTOM = 'custom', 'Custom Issuance'
        BUNDLE = 'bundle', 'Bundle Completion'
        WORKSHOP = 'workshop', 'Workshop Attendance'
    
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.COURSE)
    source_id = models.UUIDField(help_text="ID of the course, assessment, program, etc.")
    source_title = models.CharField(max_length=300, help_text="Title at time of issuance")
    
    # Certificate identification
    certificate_number = models.CharField(max_length=100, unique=True, db_index=True)
    credential_id = models.CharField(max_length=100, unique=True, db_index=True)
    # Format: CERT-{YEAR}-{SEQUENTIAL} or UUID
    
    # Status
    status = models.CharField(max_length=20, choices=CertificateStatus.choices, default=CertificateStatus.PENDING, db_index=True)
    visibility = models.CharField(max_length=20, choices=CertificateVisibility.choices, default=CertificateVisibility.LINK_ONLY)
    
    # Dates
    issue_date = models.DateTimeField(default=timezone.now)
    completion_date = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.TextField(blank=True)
    
    # Data snapshot (for verification integrity)
    certificate_data = models.JSONField(default=dict, blank=True)
    # Contains all variables used in template at generation time
    
    # Generated files
    pdf_file = models.FileField(upload_to='certificates/pdf/', null=True, blank=True)
    pdf_size = models.IntegerField(default=0)
    image_file = models.FileField(upload_to='certificates/images/', null=True, blank=True)
    qr_code_file = models.FileField(upload_to='certificates/qr/', null=True, blank=True)
    
    # Verification
    verification_url = models.URLField(blank=True)
    public_verification_page = models.BooleanField(default=True)
    blockchain_tx_hash = models.CharField(max_length=100, blank=True)
    blockchain_network = models.CharField(max_length=50, blank=True)
    
    # Signatures
    signatures = models.JSONField(default=list, blank=True)
    # [{"role": "instructor", "name": "John Doe", "title": "Senior Instructor", "signed_at": "2024-01-15T10:00:00Z", "signature_image": "url"}]
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    language = models.CharField(max_length=10, default='en')
    
    # Audit
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_certificates')
    generated_at = models.DateTimeField(null=True, blank=True)
    generation_error = models.TextField(blank=True)
    regeneration_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['credential_id']),
            models.Index(fields=['certificate_number']),
            models.Index(fields=['status', 'issue_date']),
        ]
    
    def __str__(self):
        return f"Certificate {self.certificate_number} - {self.student.display_name}"
    
    def get_verification_url(self):
        if self.verification_url:
            return self.verification_url
        template = self.template
        if template and template.verification_url_template:
            return template.verification_url_template.format(credential_id=self.credential_id)
        return ''
    
    def is_valid(self):
        if self.status != CertificateStatus.ISSUED:
            return False
        if self.expiry_date and timezone.now() > self.expiry_date:
            return False
        return True
    
    def revoke(self, reason, revoked_by):
        self.status = CertificateStatus.REVOKED
        self.revoked_at = timezone.now()
        self.revoked_reason = reason
        self.save(update_fields=['status', 'revoked_at', 'revoked_reason', 'updated_at'])


class CertificateBatch(models.Model):
    """Bulk certificate generation for courses/programs."""
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partially Completed'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    template = models.ForeignKey(CertificateTemplate, on_delete=models.PROTECT, related_name='batches')
    
    source_type = models.CharField(max_length=20, choices=Certificate.SourceType.choices)
    source_id = models.UUIDField()
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Filters for selecting recipients
    recipient_filter = models.JSONField(default=dict, blank=True)
    # {"course_id": "...", "min_score": 70, "status": "completed"}
    
    total_recipients = models.IntegerField(default=0)
    processed_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    
    # Generation settings
    issue_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField(null=True, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)
    
    # Output
    zip_file = models.FileField(upload_to='certificates/batches/', null=True, blank=True)
    error_log = models.TextField(blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_certificate_batches')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Batch: {self.name} ({self.status})"


class CertificateVerification(models.Model):
    """Public verification records for certificate authenticity."""
    
    certificate = models.OneToOneField(Certificate, on_delete=models.CASCADE, related_name='verification_record')
    
    # Public data (what's shown on verification page)
    student_name = models.CharField(max_length=200)
    student_email_hash = models.CharField(max_length=64)  # SHA256 hash
    course_title = models.CharField(max_length=300)
    issue_date = models.DateTimeField()
    expiry_date = models.DateTimeField(null=True, blank=True)
    credential_id = models.CharField(max_length=100, db_index=True)
    certificate_number = models.CharField(max_length=100)
    template_name = models.CharField(max_length=200)
    
    # Verification status
    is_verified = models.BooleanField(default=True)
    verification_count = models.IntegerField(default=0)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_verified_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Blockchain verification
    blockchain_verified = models.BooleanField(default=False)
    blockchain_tx_hash = models.CharField(max_length=100, blank=True)
    blockchain_network = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['credential_id']),
            models.Index(fields=['certificate_number']),
        ]
    
    def __str__(self):
        return f"Verification for {self.certificate_number}"


class CertificateShare(models.Model):
    """Track certificate sharing (social, email, download)."""
    
    class ShareType(models.TextChoices):
        DOWNLOAD = 'download', 'Download'
        EMAIL = 'email', 'Email'
        LINKEDIN = 'linkedin', 'LinkedIn'
        TWITTER = 'twitter', 'Twitter/X'
        FACEBOOK = 'facebook', 'Facebook'
        LINK_COPY = 'link_copy', 'Copy Link'
        QR_SCAN = 'qr_scan', 'QR Scan'
        VERIFICATION_VIEW = 'verification_view', 'Verification Page View'
    
    certificate = models.ForeignKey(Certificate, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='certificate_shares')
    share_type = models.CharField(max_length=20, choices=ShareType.choices)
    referrer = models.URLField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['certificate', 'share_type']),
            models.Index(fields=['user', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.certificate.certificate_number} - {self.share_type}"


class CertificateSkill(models.Model):
    """Skills/competencies associated with certificates."""
    
    certificate = models.ForeignKey(Certificate, on_delete=models.CASCADE, related_name='skills')
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    proficiency_level = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('expert', 'Expert'),
        ],
        default='intermediate'
    )
    description = models.TextField(blank=True)
    is_verified = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return f"{self.certificate.certificate_number} - {self.name}"


class CertificateSignature(models.Model):
    """Digital signatures for certificates."""
    
    certificate = models.ForeignKey(Certificate, on_delete=models.CASCADE, related_name='certificate_signatures')
    signer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='signed_certificates')
    role = models.CharField(max_length=50)  # instructor, director, registrar
    name = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    signature_image = models.ImageField(upload_to='certificates/signatures/', null=True, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_required = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('certificate', 'signer', 'role')
    
    def __str__(self):
        return f"{self.name} ({self.role}) signed {self.certificate.certificate_number}"


class OrganizationProfile(models.Model):
    """Organization settings for certificate branding."""
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    logo = models.ImageField(upload_to='certificates/org/', null=True, blank=True)
    seal = models.ImageField(upload_to='certificates/org/', null=True, blank=True)
    website = models.URLField(blank=True)
    verification_domain = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    # Default signatories
    default_signatories = models.JSONField(default=list, blank=True)
    # [{"role": "director", "name": "Jane Smith", "title": "Director of Education"}]
    
    # Blockchain
    blockchain_network = models.CharField(max_length=50, default='polygon')
    blockchain_contract = models.CharField(max_length=100, blank=True)
    blockchain_enabled = models.BooleanField(default=False)
    
    # Settings
    default_template = models.ForeignKey(CertificateTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    certificate_number_format = models.CharField(max_length=50, default='CERT-{YEAR}-{SEQ:06d}')
    credential_id_format = models.CharField(max_length=50, default='CRED-{UUID}')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Organization Profiles"
    
    def __str__(self):
        return self.name