from django.utils import timezone
from rest_framework import serializers

from certificate.models import (
    CertificateTemplate, Certificate, CertificateBatch,
    CertificateVerification, CertificateShare, CertificateSkill,
    CertificateSignature, CertificateVisibility, OrganizationProfile
)
from client.serializers import MinimalUserSerializer



class CertificateTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateTemplate
        fields = [
            'id', 'name', 'slug', 'description',
            'html_template', 'css_styles',
            'orientation', 'page_width', 'page_height',
            'margin_top', 'margin_right', 'margin_bottom', 'margin_left',
            'background_image', 'logo_image', 'seal_image',
            'font_family', 'heading_font',
            'output_format', 'dpi',
            'include_qr_code', 'qr_code_size', 'verification_url_template',
            'is_default', 'is_active', 'version',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'version', 'created_at', 'updated_at']


class CertificateTemplateListSerializer(serializers.ModelSerializer):
    certificate_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CertificateTemplate
        fields = [
            'id', 'name', 'slug', 'description', 'orientation',
            'is_default', 'is_active', 'version', 'certificate_count',
            'created_at', 'updated_at'
        ]
    
    def get_certificate_count(self, obj):
        return obj.certificates.filter(status=Certificate.Status.ISSUED).count()


class CertificateTemplateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateTemplate
        fields = [
            'name', 'slug', 'description',
            'html_template', 'css_styles',
            'orientation', 'page_width', 'page_height',
            'margin_top', 'margin_right', 'margin_bottom', 'margin_left',
            'background_image', 'logo_image', 'seal_image',
            'font_family', 'heading_font',
            'output_format', 'dpi',
            'include_qr_code', 'qr_code_size', 'verification_url_template',
            'is_default', 'is_active'
        ]
    
    def validate_slug(self, value):
        if CertificateTemplate.objects.filter(slug=value).exists():
            raise serializers.ValidationError("Template with this slug already exists.")
        return value
    
    def validate_html_template(self, value):
        # Basic validation - ensure it contains required placeholders
        required = ['{{student_name}}', '{{course_title}}']
        for req in required:
            if req not in value:
                raise serializers.ValidationError(f"Template must contain {req}")
        return value


class CertificateSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateSkill
        fields = ['id', 'name', 'category', 'proficiency_level', 'description', 'is_verified', 'display_order']
        read_only_fields = ['id']


class CertificateSignatureSerializer(serializers.ModelSerializer):
    signer = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = CertificateSignature
        fields = ['id', 'signer', 'role', 'name', 'title', 'signature_image', 'signed_at', 'is_required']
        read_only_fields = ['id', 'signed_at']


class CertificateSerializer(serializers.ModelSerializer):
    student = MinimalUserSerializer(read_only=True)
    template = CertificateTemplateListSerializer(read_only=True)
    skills = CertificateSkillSerializer(many=True, read_only=True)
    signatures = CertificateSignatureSerializer(many=True, read_only=True)
    verification = serializers.SerializerMethodField()
    is_valid = serializers.BooleanField(read_only=True)
    verification_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Certificate
        fields = [
            'id', 'student', 'template', 'source_type', 'source_id', 'source_title',
            'certificate_number', 'credential_id', 'status', 'visibility',
            'issue_date', 'completion_date', 'expiry_date', 'revoked_at', 'revoked_reason',
            'certificate_data', 'pdf_file', 'pdf_size', 'image_file', 'qr_code_file',
            'verification_url', 'public_verification_page', 'blockchain_tx_hash',
            'blockchain_network', 'signatures', 'skills', 'metadata', 'language',
            'generated_by', 'generated_at', 'generation_error', 'regeneration_count',
            'is_valid', 'verification', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'student', 'certificate_number', 'credential_id', 'status',
            'issue_date', 'revoked_at', 'revoked_reason', 'pdf_file', 'pdf_size',
            'image_file', 'qr_code_file', 'verification_url', 'blockchain_tx_hash',
            'blockchain_network', 'generated_by', 'generated_at', 'generation_error',
            'regeneration_count', 'created_at', 'updated_at'
        ]
    
    def get_verification(self, obj):
        if hasattr(obj, 'verification_record'):
            return CertificateVerificationSerializer(obj.verification_record).data
        return None
    
    def get_verification_url(self, obj):
        return obj.get_verification_url()


class CertificateDetailSerializer(CertificateSerializer):
    """Extended serializer with more detail."""
    student = MinimalUserSerializer(read_only=True)
    template = CertificateTemplateSerializer(read_only=True)
    
    class Meta(CertificateSerializer.Meta):
        fields = CertificateSerializer.Meta.fields + ['pdf_file', 'image_file', 'qr_code_file']


class CertificateIssueSerializer(serializers.Serializer):
    """For issuing certificates manually or via API."""
    template_id = serializers.UUIDField()
    student_id = serializers.UUIDField()
    source_type = serializers.ChoiceField(choices=Certificate.SourceType.choices)
    source_id = serializers.UUIDField()
    source_title = serializers.CharField(max_length=300)
    completion_date = serializers.DateTimeField(required=False)
    expiry_date = serializers.DateTimeField(required=False, allow_null=True)
    custom_data = serializers.DictField(required=False, default=dict)
    visibility = serializers.ChoiceField(choices=CertificateVisibility.choices, default=CertificateVisibility.LINK_ONLY)
    language = serializers.CharField(max_length=10, default='en')
    metadata = serializers.DictField(required=False, default=dict)
    
    def validate(self, attrs):
        # Check template exists and is active
        from .models import CertificateTemplate
        template = CertificateTemplate.objects.filter(id=attrs['template_id'], is_active=True).first()
        if not template:
            raise serializers.ValidationError({"template_id": "Template not found or inactive."})
        
        # Check student exists
        from django.contrib.auth import get_user_model
        User = get_user_model()
        student = User.objects.filter(id=attrs['student_id'], is_active=True).first()
        if not student:
            raise serializers.ValidationError({"student_id": "Student not found or inactive."})
        
        # Check for existing certificate
        existing = Certificate.objects.filter(
            student_id=attrs['student_id'],
            source_type=attrs['source_type'],
            source_id=attrs['source_id'],
            status__in=[Certificate.Status.ISSUED, Certificate.Status.PENDING, Certificate.Status.GENERATING]
        ).first()
        if existing:
            raise serializers.ValidationError("Certificate already exists for this source.")
        
        attrs['template'] = template
        attrs['student'] = student
        return attrs


class CertificateBulkIssueSerializer(serializers.Serializer):
    template_id = serializers.UUIDField()
    student_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    source_type = serializers.ChoiceField(choices=Certificate.SourceType.choices)
    source_id = serializers.UUIDField()
    source_title = serializers.CharField(max_length=300)
    completion_date = serializers.DateTimeField(required=False)
    expiry_date = serializers.DateTimeField(required=False, allow_null=True)
    custom_data = serializers.DictField(required=False, default=dict)
    visibility = serializers.ChoiceField(choices=CertificateVisibility.choices, default=CertificateVisibility.LINK_ONLY)


class CertificateBatchSerializer(serializers.ModelSerializer):
    template = CertificateTemplateListSerializer(read_only=True)
    created_by = MinimalUserSerializer(read_only=True)
    progress = serializers.SerializerMethodField()
    
    class Meta:
        model = CertificateBatch
        fields = [
            'id', 'name', 'template', 'source_type', 'source_id',
            'status', 'recipient_filter', 'total_recipients',
            'processed_count', 'success_count', 'failed_count',
            'progress', 'issue_date', 'expiry_date', 'custom_data',
            'zip_file', 'error_log', 'created_by', 'started_at',
            'completed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'total_recipients', 'processed_count',
            'success_count', 'failed_count', 'zip_file', 'error_log',
            'created_by', 'started_at', 'completed_at', 'created_at', 'updated_at'
        ]
    
    def get_progress(self, obj):
        if obj.total_recipients == 0:
            return 0
        return round((obj.processed_count / obj.total_recipients) * 100, 2)


class CertificateBatchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateBatch
        fields = [
            'name', 'template', 'source_type', 'source_id',
            'recipient_filter', 'issue_date', 'expiry_date', 'custom_data'
        ]
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class CertificateVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateVerification
        fields = [
            'id', 'student_name', 'student_email_hash', 'course_title',
            'issue_date', 'expiry_date', 'credential_id', 'certificate_number',
            'template_name', 'is_verified', 'verification_count',
            'last_verified_at', 'blockchain_verified', 'blockchain_tx_hash',
            'blockchain_network', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class CertificateVerifySerializer(serializers.Serializer):
    """For public certificate verification."""
    credential_id = serializers.CharField(required=False)
    certificate_number = serializers.CharField(required=False)
    
    def validate(self, attrs):
        if not attrs.get('credential_id') and not attrs.get('certificate_number'):
            raise serializers.ValidationError("Either credential_id or certificate_number is required.")
        
        query = Certificate.objects.filter(status=Certificate.Status.ISSUED)
        if attrs.get('credential_id'):
            query = query.filter(credential_id=attrs['credential_id'])
        if attrs.get('certificate_number'):
            query = query.filter(certificate_number=attrs['certificate_number'])
        
        if not query.exists():
            raise serializers.ValidationError("Certificate not found or invalid.")
        
        cert = query.first()
        if cert.expiry_date and cert.expiry_date < timezone.now():
            raise serializers.ValidationError("Certificate has expired.")
        
        attrs['certificate'] = cert
        return attrs


class CertificateVerificationResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    certificate = CertificateSerializer()
    verification = CertificateVerificationSerializer()


class CertificateShareSerializer(serializers.ModelSerializer):
    user = MinimalUserSerializer(read_only=True)
    
    class Meta:
        model = CertificateShare
        fields = ['id', 'certificate', 'user', 'share_type', 'referrer', 'ip_address', 'created_at']
        read_only_fields = fields


class CertificateShareCreateSerializer(serializers.Serializer):
    share_type = serializers.ChoiceField(choices=CertificateShare.ShareType.choices)
    referrer = serializers.URLField(required=False, allow_blank=True)


class CertificateStatsSerializer(serializers.Serializer):
    total_issued = serializers.IntegerField()
    total_revoked = serializers.IntegerField()
    total_expired = serializers.IntegerField()
    by_source_type = serializers.DictField(child=serializers.IntegerField())
    by_template = serializers.DictField(child=serializers.IntegerField())
    by_month = serializers.ListField(child=serializers.DictField())
    recent = CertificateSerializer(many=True)


class OrganizationProfileSerializer(serializers.ModelSerializer):
    default_template = CertificateTemplateListSerializer(read_only=True)
    
    class Meta:
        model = OrganizationProfile
        fields = [
            'id', 'name', 'slug', 'logo', 'seal', 'website',
            'verification_domain', 'contact_email', 'address',
            'default_signatories', 'blockchain_network', 'blockchain_contract',
            'blockchain_enabled', 'default_template', 'certificate_number_format',
            'credential_id_format', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class OrganizationProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationProfile
        fields = [
            'name', 'logo', 'seal', 'website', 'verification_domain',
            'contact_email', 'address', 'default_signatories',
            'blockchain_network', 'blockchain_contract', 'blockchain_enabled',
            'default_template', 'certificate_number_format', 'credential_id_format',
            'is_active'
        ]


class CertificateRegenerateSerializer(serializers.Serializer):
    force = serializers.BooleanField(default=False)
    new_template_id = serializers.UUIDField(required=False, allow_null=True)