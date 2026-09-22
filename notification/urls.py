from django.urls import path
from .views import (
    NotificationTemplateViewSet, NotificationPreferenceView,
    NotificationViewSet, NotificationBatchViewSet,
    DeviceTokenViewSet, PushNotificationLogView,
    EmailNotificationLogView, TestNotificationView
)

urlpatterns = [
    # Templates (Admin)
    path('templates/', NotificationTemplateViewSet.as_view(), name='template-list'),
    path('templates/<uuid:pk>/', NotificationTemplateViewSet.as_view(), name='template-detail'),

    # Preferences
    path('preferences/', NotificationPreferenceView.as_view(), name='notification-preferences'),

    # Notifications
    path('', NotificationViewSet.as_view(), name='notification-list'),
    path('<uuid:pk>/', NotificationViewSet.as_view(), name='notification-detail'),
    path('<uuid:pk>/read/', NotificationViewSet.as_view(), name='notification-mark-read'),
    path('<uuid:pk>/unread/', NotificationViewSet.as_view(), name='notification-mark-unread'),
    path('<uuid:pk>/archive/', NotificationViewSet.as_view(), name='notification-archive'),
    path('mark-all-read/', NotificationViewSet.as_view(), name='notification-mark-all-read'),
    path('archive-all/', NotificationViewSet.as_view(), name='notification-archive-all'),
    path('stats/', NotificationViewSet.as_view(), name='notification-stats'),
    path('groups/', NotificationViewSet.as_view(), name='notification-groups'),
    path('groups/toggle/', NotificationViewSet.as_view(), name='notification-toggle-group'),

    # Batches (Admin)
    path('batches/', NotificationBatchViewSet.as_view(), name='batch-list'),
    path('batches/<uuid:pk>/', NotificationBatchViewSet.as_view(), name='batch-detail'),

    # Device Tokens
    path('devices/', DeviceTokenViewSet.as_view(), name='device-list'),
    path('devices/<uuid:pk>/', DeviceTokenViewSet.as_view(), name='device-delete'),

    # Logs (Admin)
    path('logs/push/', PushNotificationLogView.as_view(), name='push-log-list'),
    path('logs/email/', EmailNotificationLogView.as_view(), name='email-log-list'),

    # Test
    path('test/', TestNotificationView.as_view(), name='test-notification'),
]