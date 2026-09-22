from django.contrib import admin
from .models import (
    CertificateTemplate, Certificate, CertificateBatch,
    CertificateVerification, CertificateShare, CertificateSkill,
    CertificateSignature, OrganizationProfile
)


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'orientation', 'is_default', 'is_active', 'version', 'certificate_count', 'created_at']
    list_filter = ['is_default', 'is_active', 'orientation', 'output_format', 'created_at']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['version', 'created_at', 'updated_at']
    ordering = ['-is_default', 'name']
    list_per_page = 25
    
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description', 'version')}),
        ('Template', {'fields': ('html_template', 'css_styles')}),
        ('Layout', {'fields': ('orientation', 'page_width', 'page_height', 'margin_top', 'margin_right', 'margin_bottom', 'margin_left')}),
        ('Assets', {'fields': ('background_image', 'logo_image', 'seal_image')}),
        ('Fonts', {'fields': ('font_family', 'heading_font')}),
        ('Output', {'fields': ('output_format', 'dpi', 'include_qr_code', 'qr_code_size', 'verification_url_template')}),
        ('Settings', {'fields': ('is_default', 'is_active')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    def certificate_count(self, obj):
        return obj.certificates.filter(status=Certificate.Status.ISSUED).count()
    certificate_count.short_description = 'Issued Certificates'
    
    def has_delete_permission(self, request, obj=None):
        if obj and obj.certificates.filter(status=Certificate.Status.ISSUED).exists():
            return False
        return super().has_delete_permission(request, obj)


class CertificateSkillInline(admin.TabularInline):
    model = CertificateSkill
    extra = 0
    fields = ['name', 'category', 'proficiency_level', 'is_verified', 'display_order']


class CertificateSignatureInline(admin.TabularInline):
    model = CertificateSignature
    extra = 0
    raw_id_fields = ['signer']
    readonly_fields = ['signed_at', 'ip_address']
    fields = ['signer', 'role', 'name', 'title', 'signature_image', 'is_required']


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['certificate_number', 'credential_id', 'student', 'source_type', 'source_title', 'status', 'visibility', 'issue_date', 'expiry_date']
    list_filter = ['status', 'visibility', 'source_type', 'template', 'issue_date', 'expiry_date']
    search_fields = ['certificate_number', 'credential_id', 'student__display_name', 'student__email', 'source_title']
    raw_id_fields = ['student', 'template', 'generated_by']
    readonly_fields = [
        'certificate_number', 'credential_id', 'status', 'issue_date',
        'revoked_at', 'revoked_reason', 'pdf_file', 'pdf_size', 'image_file',
        'qr_code_file', 'verification_url', 'blockchain_tx_hash', 'blockchain_network',
        'generated_by', 'generated_at', 'generation_error', 'regeneration_count',
        'created_at', 'updated_at'
    ]
    ordering = ['-issue_date']
    list_per_page = 25
    date_hierarchy = 'issue_date'
    inlines = [CertificateSkillInline, CertificateSignatureInline]
    
    fieldsets = (
        (None, {'fields': ('student', 'template', 'source_type', 'source_id', 'source_title')}),
        ('Identification', {'fields': ('certificate_number', 'credential_id', 'status', 'visibility')}),
        ('Dates', {'fields': ('issue_date', 'completion_date', 'expiry_date', 'revoked_at', 'revoked_reason')}),
        ('Data', {'fields': ('certificate_data', 'metadata', 'language'), 'classes': ('collapse',)}),
        ('Files', {'fields': ('pdf_file', 'pdf_size', 'image_file', 'qr_code_file')}),
        ('Verification', {'fields': ('verification_url', 'public_verification_page', 'blockchain_tx_hash', 'blockchain_network')}),
        ('Signatures', {'fields': ('signatures',), 'classes': ('collapse',)}),
        ('Generation', {'fields': ('generated_by', 'generated_at', 'generation_error', 'regeneration_count'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    actions = ['revoke_certificates', 'regenerate_certificates', 'make_public', 'make_private']
    
    def revoke_certificates(self, request, queryset):
        for cert in queryset.filter(status=Certificate.Status.ISSUED):
            cert.revoke('Revoked by admin', request.user)
    revoke_certificates.short_description = "Revoke selected certificates"
    
    def regenerate_certificates(self, request, queryset):
        for cert in queryset.filter(status__in=[Certificate.Status.ISSUED, Certificate.Status.FAILED]):
            cert.status = Certificate.Status.GENERATING
            cert.generated_at = timezone.now()
            cert.regeneration_count += 1
            cert.generation_error = ''
            cert.save(update_fields=['status', 'generated_at', 'regeneration_count', 'generation_error', 'updated_at'])
    regenerate_certificates.short_description = "Regenerate selected certificates"
    
    def make_public(self, request, queryset):
        queryset.update(visibility=Certificate.Visibility.PUBLIC)
    make_public.short_description = "Make selected certificates public"
    
    def make_private(self, request, queryset):
        queryset.update(visibility=Certificate.Visibility.PRIVATE)
    make_private.short_description = "Make selected certificates private"


@admin.register(CertificateBatch)
class CertificateBatchAdmin(admin.ModelAdmin):
    list_display = ['name', 'template', 'source_type', 'source_id', 'status', 'total_recipients', 'processed_count', 'success_count', 'failed_count', 'created_by', 'created_at']
    list_filter = ['status', 'source_type', 'template', 'created_at']
    search_fields = ['name', 'template__name', 'source_id']
    raw_id_fields = ['template', 'created_by']
    readonly_fields = [
        'total_recipients', 'processed_count', 'success_count', 'failed_count',
        'zip_file', 'error_log', 'created_by', 'started_at', 'completed_at',
        'created_at', 'updated_at'
    ]
    ordering = ['-created_at']
    list_per_page = 25
    
    fieldsets = (
        (None, {'fields': ('name', 'template', 'source_type', 'source_id')}),
        ('Filters', {'fields': ('recipient_filter',)}),
        ('Status', {'fields': ('status', 'total_recipients', 'processed_count', 'success_count', 'failed_count', 'progress')}),
        ('Dates', {'fields': ('issue_date', 'expiry_date')}),
        ('Custom Data', {'fields': ('custom_data',), 'classes': ('collapse',)}),
        ('Output', {'fields': ('zip_file', 'error_log')}),
        ('Meta', {'fields': ('created_by', 'started_at', 'completed_at', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    actions = ['process_batches', 'retry_failed']
    
    def process_batches(self, request, queryset):
        for batch in queryset.filter(status=CertificateBatch.Status.PENDING):
            batch.status = CertificateBatch.Status.PROCESSING
            batch.started_at = timezone.now()
            batch.save()
            # Would trigger Celery task in production
    process_batches.short_description = "Process selected batches"
    
    def retry_failed(self, request, queryset):
        queryset.filter(status=CertificateBatch.Status.FAILED).update(
            status=CertificateBatch.Status.PENDING,
            error_log=''
        )
    retry_failed.short_description = "Retry failed batches"


@admin.register(CertificateVerification)
class CertificateVerificationAdmin(admin.ModelAdmin):
    list_display = ['certificate_number', 'credential_id', 'student_name', 'course_title', 'is_verified', 'verification_count', 'last_verified_at', 'blockchain_verified']
    list_filter = ['is_verified', 'blockchain_verified', 'blockchain_network', 'created_at']
    search_fields = ['certificate_number', 'credential_id', 'student_name', 'course_title']
    raw_id_fields = ['certificate']
    readonly_fields = ['verification_count', 'last_verified_at', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 50


@admin.register(CertificateShare)
class CertificateShareAdmin(admin.ModelAdmin):
    list_display = ['certificate', 'user', 'share_type', 'created_at']
    list_filter = ['share_type', 'created_at']
    search_fields = ['certificate__certificate_number', 'user__display_name']
    raw_id_fields = ['certificate', 'user']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    list_per_page = 100
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CertificateSkill)
class CertificateSkillAdmin(admin.ModelAdmin):
    list_display = ['certificate', 'name', 'category', 'proficiency_level', 'is_verified', 'display_order']
    list_filter = ['category', 'proficiency_level', 'is_verified']
    search_fields = ['name', 'certificate__certificate_number', 'certificate__student__display_name']
    raw_id_fields = ['certificate']
    ordering = ['certificate', 'display_order']


@admin.register(CertificateSignature)
class CertificateSignatureAdmin(admin.ModelAdmin):
    list_display = ['certificate', 'signer', 'role', 'name', 'title', 'signed_at']
    list_filter = ['role', 'is_required', 'signed_at']
    search_fields = ['name', 'certificate__certificate_number', 'signer__display_name']
    raw_id_fields = ['certificate', 'signer']
    readonly_fields = ['signed_at', 'ip_address']
    ordering = ['-signed_at']


@admin.register(OrganizationProfile)
class OrganizationProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'website', 'blockchain_enabled', 'is_active', 'created_at']
    list_filter = ['is_active', 'blockchain_enabled', 'blockchain_network']
    search_fields = ['name', 'slug', 'website']
    raw_id_fields = ['default_template']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'logo', 'seal', 'website', 'contact_email', 'address')}),
        ('Verification', {'fields': ('verification_domain',)}),
        ('Signatories', {'fields': ('default_signatories',), 'classes': ('collapse',)}),
        ('Blockchain', {'fields': ('blockchain_network', 'blockchain_contract', 'blockchain_enabled')}),
        ('Defaults', {'fields': ('default_template', 'certificate_number_format', 'credential_id_format')}),
        ('Status', {'fields': ('is_active',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    
    def has_add_permission(self, request):
        return not OrganizationProfile.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False


from django.utils import timezone