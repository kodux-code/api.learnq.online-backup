from django.urls import path
from certificate.views import (
    CertificateTemplateViewSet, CertificateViewSet, CertificateVerificationView,
    CertificatePublicView, CertificateBatchViewSet, CertificateStatsView,
    OrganizationProfileView, CertificateSkillViewSet
)

urlpatterns = [
    # Templates (Admin)
    path('templates/', CertificateTemplateViewSet.as_view(), name='template-list'),
    path('templates/<uuid:pk>/', CertificateTemplateViewSet.as_view(), name='template-detail'),
    path('templates/<uuid:pk>/set-default/', CertificateTemplateViewSet.as_view(), name='template-set-default'),
    
    # Certificates
    path('', CertificateViewSet.as_view(), name='certificate-list'),
    path('<uuid:pk>/', CertificateViewSet.as_view(), name='certificate-detail'),
    path('<uuid:pk>/regenerate/', CertificateViewSet.as_view(), name='certificate-regenerate'),
    path('<uuid:pk>/revoke/', CertificateViewSet.as_view(), name='certificate-revoke'),
    path('<uuid:pk>/share/', CertificateViewSet.as_view(), name='certificate-share'),
    path('<uuid:pk>/shares/', CertificateViewSet.as_view(), name='certificate-shares'),
    path('<uuid:pk>/download/', CertificateViewSet.as_view(), name='certificate-download'),
    path('bulk-issue/', CertificateViewSet.as_view(), name='certificate-bulk-issue'),
    
    # Verification
    path('verify/', CertificateVerificationView.as_view(), name='certificate-verify'),
    path('public/<str:credential_id>/', CertificatePublicView.as_view(), name='certificate-public'),
    
    # Batches (Admin)
    path('batches/', CertificateBatchViewSet.as_view(), name='batch-list'),
    path('batches/<uuid:pk>/', CertificateBatchViewSet.as_view(), name='batch-detail'),
    
    # Stats (Admin)
    path('stats/', CertificateStatsView.as_view(), name='certificate-stats'),
    
    # Organization
    path('organization/', OrganizationProfileView.as_view(), name='organization-profile'),
    
    # Skills
    path('<uuid:certificate_id>/skills/', CertificateSkillViewSet.as_view(), name='skill-list'),
    path('<uuid:certificate_id>/skills/<uuid:pk>/', CertificateSkillViewSet.as_view(), name='skill-detail'),
]