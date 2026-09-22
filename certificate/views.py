from django.db.models import Count, Q, Sum
from rest_framework.decorators import action
import uuid
import hashlib
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models.functions import TruncMonth
import uuid
import hashlib

from .models import (
    CertificateTemplate, Certificate, CertificateBatch,
    CertificateVerification, CertificateShare, CertificateSkill,
    CertificateSignature, OrganizationProfile
)
from .serializers import (
    CertificateSkillSerializer, CertificateTemplateSerializer, CertificateTemplateListSerializer, CertificateTemplateCreateSerializer,
    CertificateSerializer, CertificateDetailSerializer, CertificateIssueSerializer,
    CertificateBulkIssueSerializer, CertificateBatchSerializer, CertificateBatchCreateSerializer,
    CertificateVerificationSerializer, CertificateVerifySerializer, CertificateVerificationResponseSerializer,
    CertificateShareSerializer, CertificateShareCreateSerializer,
    CertificateStatsSerializer, OrganizationProfileSerializer, OrganizationProfileUpdateSerializer,
    CertificateRegenerateSerializer
)
from .tasks import generate_certificate_pdf, process_certificate_batch
from client.permissions import IsAccountOwnerOrStaff

User = get_user_model()


class CertificateTemplateViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'slug', 'description']
    ordering_fields = ['name', 'created_at', 'version']
    ordering = ['-is_default', 'name']
    
    def get_queryset(self):
        return CertificateTemplate.objects.filter(is_active=True)
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CertificateTemplateCreateSerializer
        if self.action == 'list':
            return CertificateTemplateListSerializer
        return CertificateTemplateSerializer
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        if serializer.validated_data.get('is_default'):
            CertificateTemplate.objects.filter(is_default=True).update(is_default=False)
        
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        if serializer.validated_data.get('is_default'):
            CertificateTemplate.objects.filter(is_default=True).exclude(id=instance.id).update(is_default=False)
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.certificates.filter(status=Certificate.Status.ISSUED).exists():
            return Response({"error": "Cannot delete template with issued certificates."}, status=status.HTTP_400_BAD_REQUEST)
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, *args, **kwargs):
        instance = self.get_object()
        CertificateTemplate.objects.update(is_default=False)
        instance.is_default = True
        instance.save(update_fields=['is_default'])
        return Response({"detail": "Template set as default."})


class CertificateViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['certificate_number', 'credential_id', 'source_title', 'student__display_name']
    ordering_fields = ['issue_date', 'created_at', 'status']
    ordering = ['-issue_date']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Certificate.objects.select_related('student', 'template').prefetch_related('skills', 'signatures')
        return Certificate.objects.filter(student=user).select_related('template').prefetch_related('skills', 'signatures')
    
    def get_serializer_class(self):
        if self.action in ['create', 'bulk_issue']:
            return CertificateIssueSerializer
        if self.action == 'retrieve':
            return CertificateDetailSerializer
        return CertificateSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'bulk_issue', 'regenerate']:
            return [IsAuthenticated()]
        if self.action == 'verify':
            return [AllowAny()]
        return [IsAuthenticated()]
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        source_type = request.query_params.get('source_type')
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        
        template_id = request.query_params.get('template')
        if template_id:
            queryset = queryset.filter(template_id=template_id)
        
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        cert = self._issue_certificate(
            student=serializer.validated_data['student'],
            template=serializer.validated_data['template'],
            source_type=serializer.validated_data['source_type'],
            source_id=serializer.validated_data['source_id'],
            source_title=serializer.validated_data['source_title'],
            completion_date=serializer.validated_data.get('completion_date'),
            expiry_date=serializer.validated_data.get('expiry_date'),
            custom_data=serializer.validated_data.get('custom_data', {}),
            visibility=serializer.validated_data.get('visibility'),
            language=serializer.validated_data.get('language', 'en'),
            metadata=serializer.validated_data.get('metadata', {}),
            generated_by=request.user
        )
        
        return Response(CertificateDetailSerializer(cert, context={'request': request}).data, status=status.HTTP_201_CREATED)
    
    def _issue_certificate(self, student, template, source_type, source_id, source_title,
                          completion_date, expiry_date, custom_data, visibility, language, metadata, generated_by):
        
        org = OrganizationProfile.objects.filter(is_active=True).first()
        
        if org and org.certificate_number_format:
            from django.db.models import Max
            year = timezone.now().year
            seq = Certificate.objects.filter(issue_date__year=year).aggregate(max_seq=Max('certificate_number'))['max_seq']
            cert_number = f"CERT-{year}-{Certificate.objects.filter(issue_date__year=year).count() + 1:06d}"
        else:
            cert_number = f"CERT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        credential_id = f"CRED-{uuid.uuid4().hex[:12].upper()}"
        
        cert_data = {
            'student_name': student.display_name,
            'student_email': student.email,
            'student_id': str(student.id),
            'course_title': source_title,
            'completion_date': completion_date.isoformat() if completion_date else timezone.now().isoformat(),
            'issue_date': timezone.now().isoformat(),
            'expiry_date': expiry_date.isoformat() if expiry_date else None,
            'credential_id': credential_id,
            'certificate_number': cert_number,
            'organization_name': org.name if org else 'LearnQ',
            'verification_url': template.verification_url_template.format(credential_id=credential_id),
            **custom_data
        }
        
        cert = Certificate.objects.create(
            student=student,
            template=template,
            source_type=source_type,
            source_id=source_id,
            source_title=source_title,
            certificate_number=cert_number,
            credential_id=credential_id,
            status=Certificate.Status.PENDING,
            visibility=visibility,
            completion_date=completion_date or timezone.now(),
            expiry_date=expiry_date,
            certificate_data=cert_data,
            metadata=metadata,
            language=language,
            generated_by=generated_by
        )
        
        self._generate_certificate_async(cert)
        
        return cert
    
    def _generate_certificate_async(self, cert):
        generate_certificate_pdf.delay(str(cert.id))
    
    def _hash_email(self, email):
        import hashlib
        return hashlib.sha256(email.lower().encode()).hexdigest()
    
    @action(detail=False, methods=['post'])
    def bulk_issue(self, request, *args, **kwargs):
        serializer = CertificateBulkIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        template = CertificateTemplate.objects.get(id=serializer.validated_data['template_id'], is_active=True)
        students = User.objects.filter(id__in=serializer.validated_data['student_ids'], is_active=True)
        
        results = []
        for student in students:
            try:
                cert = self._issue_certificate(
                    student=student,
                    template=template,
                    source_type=serializer.validated_data['source_type'],
                    source_id=serializer.validated_data['source_id'],
                    source_title=serializer.validated_data['source_title'],
                    completion_date=serializer.validated_data.get('completion_date'),
                    expiry_date=serializer.validated_data.get('expiry_date'),
                    custom_data=serializer.validated_data.get('custom_data', {}),
                    visibility=serializer.validated_data.get('visibility'),
                    language='en',
                    metadata={},
                    generated_by=request.user
                )
                results.append({'student_id': str(student.id), 'certificate_id': str(cert.id), 'status': 'issued'})
            except Exception as e:
                results.append({'student_id': str(student.id), 'status': 'failed', 'error': str(e)})
        
        return Response({'results': results}, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def regenerate(self, request, *args, **kwargs):
        cert = self.get_object()
        serializer = CertificateRegenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        if cert.status == Certificate.Status.GENERATING:
            return Response({"error": "Certificate is already being generated."}, status=status.HTTP_400_BAD_REQUEST)
        
        cert.regeneration_count += 1
        cert.status = Certificate.Status.GENERATING
        cert.generated_at = timezone.now()
        cert.generation_error = ''
        if serializer.validated_data.get('new_template_id'):
            cert.template_id = serializer.validated_data['new_template_id']
        cert.save(update_fields=['regeneration_count', 'status', 'generated_at', 'generation_error', 'template', 'updated_at'])
        
        self._generate_certificate_async(cert)
        
        return Response(CertificateDetailSerializer(cert, context={'request': request}).data)
    
    @action(detail=True, methods=['post'])
    def revoke(self, request, *args, **kwargs):
        cert = self.get_object()
        reason = request.data.get('reason', '')
        
        if not request.user.is_staff and cert.student != request.user:
            return Response({"error": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
        
        if cert.status == Certificate.Status.REVOKED:
            return Response({"error": "Already revoked."}, status=status.HTTP_400_BAD_REQUEST)
        
        cert.revoke(reason, request.user)
        
        if hasattr(cert, 'verification_record'):
            cert.verification_record.is_verified = False
            cert.verification_record.save(update_fields=['is_verified'])
        
        return Response({"detail": "Certificate revoked."})
    
    @action(detail=True, methods=['post'])
    def share(self, request, *args, **kwargs):
        cert = self.get_object()
        serializer = CertificateShareCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        share = CertificateShare.objects.create(
            certificate=cert,
            user=request.user,
            share_type=serializer.validated_data['share_type'],
            referrer=serializer.validated_data.get('referrer', ''),
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response(CertificateShareSerializer(share).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def shares(self, request, *args, **kwargs):
        cert = self.get_object()
        shares = cert.shares.all()[:50]
        return Response(CertificateShareSerializer(shares, many=True).data)
    
    @action(detail=True, methods=['get'])
    def download(self, request, *args, **kwargs):
        cert = self.get_object()
        
        if cert.status != Certificate.Status.ISSUED:
            return Response({"error": "Certificate not issued."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not cert.pdf_file:
            return Response({"error": "PDF not available."}, status=status.HTTP_404_NOT_FOUND)
        
        CertificateShare.objects.create(
            certificate=cert,
            user=request.user,
            share_type=CertificateShare.ShareType.DOWNLOAD,
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return Response({
            'url': cert.pdf_file.url,
            'filename': f"{cert.certificate_number}.pdf"
        })
    
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class CertificateVerificationView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = CertificateVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        cert = serializer.validated_data['certificate']
        
        if hasattr(cert, 'verification_record'):
            cert.verification_record.verification_count += 1
            cert.verification_record.last_verified_at = timezone.now()
            cert.verification_record.last_verified_ip = self._get_client_ip(request)
            cert.verification_record.save(update_fields=['verification_count', 'last_verified_at', 'last_verified_ip'])
        
        return Response(CertificateVerificationResponseSerializer({
            'valid': True,
            'certificate': cert,
            'verification': cert.verification_record
        }).data)
    
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class CertificatePublicView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request, credential_id):
        try:
            cert = Certificate.objects.select_related('student', 'template').get(
                credential_id=credential_id,
                status=Certificate.Status.ISSUED,
                visibility__in=[Certificate.Visibility.PUBLIC, Certificate.Visibility.LINK_ONLY]
            )
        except Certificate.DoesNotExist:
            return Response({"error": "Certificate not found or not publicly visible."}, status=status.HTTP_404_NOT_FOUND)
        
        if cert.expiry_date and cert.expiry_date < timezone.now():
            return Response({"error": "Certificate has expired."}, status=status.HTTP_410_GONE)
        
        if hasattr(cert, 'verification_record'):
            cert.verification_record.verification_count += 1
            cert.verification_record.last_verified_at = timezone.now()
            cert.verification_record.save(update_fields=['verification_count', 'last_verified_at'])
        
        return Response({
            'certificate': CertificateVerificationSerializer(cert.verification_record).data,
            'student_name': cert.student.display_name,
            'template': {
                'name': cert.template.name,
                'background_image': cert.template.background_image.url if cert.template.background_image else None,
                'logo_image': cert.template.logo_image.url if cert.template.logo_image else None,
            },
            'data': cert.certificate_data
        })


class CertificateBatchViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']
    
    def get_queryset(self):
        return CertificateBatch.objects.select_related('template', 'created_by')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CertificateBatchCreateSerializer
        return CertificateBatchSerializer
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        batch = serializer.save()
        
        process_certificate_batch.delay(str(batch.id))
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CertificateStatsView(APIView):
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        now = timezone.now()
        
        stats = {
            'total_issued': Certificate.objects.filter(status=Certificate.Status.ISSUED).count(),
            'total_revoked': Certificate.objects.filter(status=Certificate.Status.REVOKED).count(),
            'total_expired': Certificate.objects.filter(
                status=Certificate.Status.ISSUED,
                expiry_date__lt=now
            ).count(),
            'by_source_type': dict(
                Certificate.objects.filter(status=Certificate.Status.ISSUED)
                .values('source_type')
                .annotate(count=Count('id'))
                .values_list('source_type', 'count')
            ),
            'by_template': dict(
                Certificate.objects.filter(status=Certificate.Status.ISSUED)
                .values('template__name')
                .annotate(count=Count('id'))
                .values_list('template__name', 'count')
            ),
            'by_month': list(
                Certificate.objects.filter(status=Certificate.Status.ISSUED)
                .annotate(month=TruncMonth('issue_date'))
                .values('month')
                .annotate(count=Count('id'))
                .order_by('month')
            ),
            'recent': CertificateSerializer(
                Certificate.objects.filter(status=Certificate.Status.ISSUED)
                .select_related('student', 'template')
                .order_by('-issue_date')[:10],
                many=True
            ).data
        }
        
        return Response(CertificateStatsSerializer(stats).data)


class OrganizationProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    queryset = OrganizationProfile.objects.all()
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return OrganizationProfileUpdateSerializer
        return OrganizationProfileSerializer
    
    def get_object(self):
        obj, _ = OrganizationProfile.objects.get_or_create(pk=1)
        return obj


class CertificateSkillViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsAccountOwnerOrStaff]
    
    def get_queryset(self):
        cert_id = self.kwargs['certificate_id']
        return CertificateSkill.objects.filter(certificate_id=cert_id)
    
    def get_serializer_class(self):
        return CertificateSkillSerializer
    
    def list(self, request, certificate_id):
        cert = get_object_or_404(Certificate, id=certificate_id)
        self.check_object_permissions(request, cert)
        skills = self.get_queryset()
        return Response(CertificateSkillSerializer(skills, many=True).data)
    
    def create(self, request, certificate_id):
        cert = get_object_or_404(Certificate, id=certificate_id)
        self.check_object_permissions(request, cert)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(certificate=cert)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, certificate_id, pk):
        cert = get_object_or_404(Certificate, id=certificate_id)
        self.check_object_permissions(request, cert)
        skill = get_object_or_404(CertificateSkill, id=pk, certificate=cert)
        serializer = self.get_serializer(skill, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def destroy(self, request, certificate_id, pk):
        cert = get_object_or_404(Certificate, id=certificate_id)
        self.check_object_permissions(request, cert)
        skill = get_object_or_404(CertificateSkill, id=pk, certificate=cert)
        skill.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
