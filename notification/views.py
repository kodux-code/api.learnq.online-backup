from django.db.models import Count, Q, F
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import action
from rest_framework import generics, request, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType

from .models import (
    NotificationPriority, NotificationTemplate, NotificationPreference, Notification,
    NotificationBatch, DeviceToken, PushNotificationLog,
    EmailNotificationLog, InAppNotificationGroup
)
from .serializers import (
    NotificationTemplateSerializer, NotificationTemplateCreateSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer, NotificationListSerializer, NotificationCreateSerializer,
    NotificationBatchSerializer, NotificationBatchCreateSerializer,
    DeviceTokenSerializer, DeviceTokenRegisterSerializer,
    PushNotificationLogSerializer, EmailNotificationLogSerializer,
    InAppNotificationGroupSerializer, NotificationStatsSerializer
)
from client.permissions import IsAccountOwnerOrStaff


class NotificationTemplateViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'slug', 'description']
    ordering = ['name']

    def get_queryset(self):
        return NotificationTemplate.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return NotificationTemplateCreateSerializer
        return NotificationTemplateSerializer

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
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationPreferenceSerializer

    def get_object(self):
        preference, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return preference


class NotificationViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'priority', 'category']
    ordering = ['-created_at']

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).select_related('sender', 'template', 'content_type')

    def get_serializer_class(self):
        if self.action == 'create':
            return NotificationCreateSerializer
        if self.action == 'list':
            return NotificationListSerializer
        return NotificationSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Filters
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        unread_only = request.query_params.get('unread_only')
        if unread_only == 'true':
            queryset = queryset.exclude(status=Notification.Status.READ)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != Notification.Status.READ:
            instance.mark_read()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self._send_notifications(serializer.validated_data)
        return Response({'detail': 'Notifications queued for delivery.'}, status=status.HTTP_201_CREATED)

    def _send_notifications(self, validated_data):
        # This would integrate with Celery for async delivery
        # For now, create notifications directly
        recipient_ids = validated_data.pop('recipient_ids', [])
        recipient_filter = validated_data.pop('recipient_filter', {})

        from django.contrib.auth import get_user_model
        User = get_user_model()

        if recipient_ids:
            recipients = User.objects.filter(id__in=recipient_ids)
        else:
            recipients = User.objects.filter(**recipient_filter)

        template = validated_data.get('template')
        for recipient in recipients:
            Notification.objects.create(
                recipient=recipient,
                sender=request.user if hasattr(request, 'user') else None,
                template=template,
                **validated_data
            )

    @action(detail=True, methods=['post'])
    def mark_read(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.mark_read()
        return Response({'detail': 'Marked as read.'})

    @action(detail=True, methods=['post'])
    def mark_unread(self, request, *args, **kwargs):
        notification = self.get_object()
        if notification.status == Notification.Status.READ:
            notification.status = Notification.Status.SENT
            notification.read_at = None
            notification.save(update_fields=['status', 'read_at', 'updated_at'])
        return Response({'detail': 'Marked as unread.'})

    @action(detail=True, methods=['post'])
    def archive(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.mark_archived()
        return Response({'detail': 'Archived.'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request, *args, **kwargs):
        category = request.data.get('category')
        queryset = self.get_queryset().exclude(status=Notification.Status.READ)
        if category:
            queryset = queryset.filter(category=category)
        updated = queryset.update(status=Notification.Status.READ, read_at=timezone.now())
        return Response({'detail': f'Marked {updated} notifications as read.'})

    @action(detail=False, methods=['post'])
    def archive_all(self, request, *args, **kwargs):
        category = request.data.get('category')
        queryset = self.get_queryset().exclude(status=Notification.Status.ARCHIVED)
        if category:
            queryset = queryset.filter(category=category)
        updated = queryset.update(status=Notification.Status.ARCHIVED, archived_at=timezone.now())
        return Response({'detail': f'Archived {updated} notifications.'})

    @action(detail=False, methods=['get'])
    def stats(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        stats = {
            'total': queryset.count(),
            'unread': queryset.exclude(status=Notification.Status.READ).count(),
            'by_category': dict(queryset.values('category').annotate(count=Count('id')).values_list('category', 'count')),
            'by_priority': dict(queryset.values('priority').annotate(count=Count('id')).values_list('priority', 'count')),
            'by_channel': {},
        }

        serializer = NotificationStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def groups(self, request, *args, **kwargs):
        groups = InAppNotificationGroup.objects.filter(user=request.user)
        serializer = InAppNotificationGroupSerializer(groups, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def toggle_group(self, request, *args, **kwargs):
        category = request.data.get('category')
        if not category:
            return Response({'error': 'Category required.'}, status=status.HTTP_400_BAD_REQUEST)

        group, _ = InAppNotificationGroup.objects.get_or_create(
            user=request.user,
            category=category
        )
        group.is_expanded = not group.is_expanded
        group.save(update_fields=['is_expanded'])
        return Response(InAppNotificationGroupSerializer(group).data)


class NotificationBatchViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']

    def get_queryset(self):
        return NotificationBatch.objects.select_related('template', 'created_by')

    def get_serializer_class(self):
        if self.action == 'create':
            return NotificationBatchCreateSerializer
        return NotificationBatchSerializer

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
        batch = serializer.save(created_by=request.user)

        # Queue for processing (would use Celery in production)
        self._process_batch(batch)

        return Response(self.get_serializer(batch).data, status=status.HTTP_201_CREATED)

    def _process_batch(self, batch):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        batch.status = NotificationBatch.Status.PROCESSING
        batch.started_at = timezone.now()
        batch.save()

        # Build queryset from filter
        queryset = User.objects.filter(is_active=True)
        filter_dict = batch.recipient_filter

        if filter_dict.get('role'):
            queryset = queryset.filter(role=filter_dict['role'])
        if filter_dict.get('is_verified') is not None:
            queryset = queryset.filter(is_verified=filter_dict['is_verified'])
        if filter_dict.get('joined_after'):
            queryset = queryset.filter(created_at__gte=filter_dict['joined_after'])
        if filter_dict.get('joined_before'):
            queryset = queryset.filter(created_at__lte=filter_dict['joined_before'])

        recipients = list(queryset)
        batch.recipient_count = len(recipients)
        batch.save()

        template = batch.template
        for recipient in recipients:
            # Check preferences
            pref, _ = NotificationPreference.objects.get_or_create(user=recipient)
            enabled_channels = [c for c in batch.channels if pref.is_channel_enabled(c)]

            if not enabled_channels:
                batch.failed_count += 1
                continue

            notification = Notification.objects.create(
                recipient=recipient,
                template=template,
                title=template.subject_template or template.name,
                message=template.body_template,
                html_message=template.html_template,
                category=template.slug,
                priority=NotificationPriority.NORMAL,
                channels=enabled_channels,
                metadata={'batch_id': str(batch.id)}
            )
            batch.sent_count += 1

        batch.status = NotificationBatch.Status.COMPLETED if batch.failed_count == 0 else NotificationBatch.Status.PARTIAL
        batch.completed_at = timezone.now()
        batch.save()


class DeviceTokenViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return DeviceTokenRegisterSerializer
        return DeviceTokenSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PushNotificationLogView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PushNotificationLogSerializer
    filter_backends = [filters.OrderingFilter]
    ordering = ['-sent_at']

    def get_queryset(self):
        return PushNotificationLog.objects.select_related('notification', 'device_token__user')


class EmailNotificationLogView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = EmailNotificationLogSerializer
    filter_backends = [filters.OrderingFilter]
    ordering = ['-sent_at']

    def get_queryset(self):
        return EmailNotificationLog.objects.select_related('notification')


class TestNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        template_slug = request.data.get('template')
        channels = request.data.get('channels', ['in_app'])

        try:
            template = NotificationTemplate.objects.get(slug=template_slug, is_active=True)
        except NotificationTemplate.DoesNotExist:
            return Response({'error': 'Template not found.'}, status=status.HTTP_404_NOT_FOUND)

        notification = Notification.objects.create(
            recipient=request.user,
            sender=request.user,
            template=template,
            title=template.subject_template or template.name,
            message=template.body_template,
            html_message=template.html_template,
            category=template.slug,
            priority=NotificationPriority.NORMAL,
            channels=channels,
            metadata={'test': True}
        )

        return Response(NotificationSerializer(notification).data, status=status.HTTP_201_CREATED)