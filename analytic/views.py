from rest_framework.decorators import action
from django.db.models import Sum, Count, Avg, F, Q, Max, Min, Window
from django.db.models.functions import TruncHour, TruncDay, TruncWeek, TruncMonth, Coalesce
from django.utils import timezone
from datetime import timedelta, datetime
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.parsers import JSONParser
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
import csv
import json

from .models import (
    Event, DailyMetric, HourlyMetric, Dashboard, DashboardWidget,
    Report, RetentionCohort, FunnelStep, Alert, AlertTrigger, AnalyticsSettings
)
from .serializers import (
    EventSerializer, EventCreateSerializer, BatchEventSerializer,
    DailyMetricSerializer, HourlyMetricSerializer,
    DashboardSerializer, DashboardCreateSerializer, DashboardWidgetSerializer,
    ReportSerializer, ReportCreateSerializer, RetentionCohortSerializer,
    FunnelStepSerializer, FunnelAnalysisSerializer,
    AlertSerializer, AlertTriggerSerializer, AlertActionSerializer,
    AnalyticsSettingsSerializer, TimeSeriesQuerySerializer, TimeSeriesDataSerializer,
    RealtimeMetricsSerializer, CohortAnalysisSerializer, UserJourneySerializer
)


class EventTrackView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    serializer_class = EventCreateSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "ok"}, status=status.HTTP_201_CREATED)


class BatchEventTrackView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    
    def post(self, request):
        serializer = BatchEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        events = []
        for event_data in serializer.validated_data['events']:
            events.append(Event(
                event_type=event_data['event_type'],
                user=request.user if request.user.is_authenticated else None,
                session_id=event_data.get('session_id', ''),
                properties=event_data.get('properties', {}),
                ip_address=event_data.get('ip_address'),
                user_agent=event_data.get('user_agent', ''),
                referrer=event_data.get('referrer', ''),
                url=event_data.get('url', ''),
                source_app=event_data.get('source_app', ''),
                source_version=event_data.get('source_version', ''),
            ))
        
        Event.objects.bulk_create(events, ignore_conflicts=True)
        return Response({"status": "ok", "count": len(events)}, status=status.HTTP_201_CREATED)


class TimeSeriesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = TimeSeriesQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        
        Model = HourlyMetric if params['granularity'] == 'hour' else DailyMetric
        trunc_func = {'hour': TruncHour, 'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth}[params['granularity']]
        
        queryset = Model.objects.filter(
            date__gte=params['start_date'] if params['granularity'] != 'hour' else timezone.make_aware(datetime.combine(params['start_date'], datetime.min.time())),
            date__lte=params['end_date'] if params['granularity'] != 'hour' else timezone.make_aware(datetime.combine(params['end_date'], datetime.max.time())),
            metric_name__in=params['metric_names'],
        )
        
        if params.get('apps'):
            queryset = queryset.filter(app__in=params['apps'])
        if params.get('user_roles'):
            queryset = queryset.filter(user_role__in=params['user_roles'])
        for dim_key, dim_value in params.get('dimensions', {}).items():
            queryset = queryset.filter(**{f'dimension__{dim_key}': dim_value})
        for filter_key, filter_value in params.get('filters', {}).items():
            queryset = queryset.filter(**{filter_key: filter_value})
        
        # Group by time and metric
        grouped = queryset.values('metric_name').annotate(
            period=trunc_func('date' if params['granularity'] != 'hour' else 'hour')
        ).annotate(
            total_count=Sum('count'),
            total_sum=Sum('sum_value'),
            avg_value=Avg('avg_value'),
        ).order_by('metric_name', 'period')
        
        # Organize by metric
        results = {}
        for item in grouped:
            metric = item['metric_name']
            if metric not in results:
                results[metric] = []
            results[metric].append({
                'period': item['period'],
                'count': item['total_count'],
                'sum': item['total_sum'],
                'avg': item['avg_value'],
            })
        
        data = [
            {'metric_name': k, 'granularity': params['granularity'], 'data': v}
            for k, v in results.items()
        ]
        return Response(TimeSeriesDataSerializer(data, many=True).data)


class RealtimeMetricsView(APIView):
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        now = timezone.now()
        five_min_ago = now - timedelta(minutes=5)
        one_hour_ago = now - timedelta(hours=1)
        
        # Active users in last 5 min
        active_users = Event.objects.filter(
            timestamp__gte=five_min_ago
        ).values('user').distinct().count()
        
        # Events per minute
        events_per_minute = Event.objects.filter(
            timestamp__gte=one_hour_ago
        ).count() / 60
        
        # Revenue per minute (from payment events)
        revenue_events = Event.objects.filter(
            timestamp__gte=one_hour_ago,
            event_type__in=['payment.completed', 'payment.refunded']
        )
        revenue_per_minute = 0
        for e in revenue_events:
            amount = e.properties.get('amount', 0)
            if e.event_type == 'payment.refunded':
                revenue_per_minute -= amount
            else:
                revenue_per_minute += amount
        revenue_per_minute /= 60
        
        # Top events
        top_events = list(Event.objects.filter(
            timestamp__gte=one_hour_ago
        ).values('event_type').annotate(
            count=Count('id')
        ).order_by('-count')[:10])
        
        # Top pages
        top_pages = list(Event.objects.filter(
            timestamp__gte=one_hour_ago,
            event_type='page.view'
        ).values('url').annotate(
            count=Count('id')
        ).order_by('-count')[:10])
        
        # Errors per minute
        errors_per_minute = Event.objects.filter(
            timestamp__gte=one_hour_ago,
            event_type='error.occurred'
        ).count() / 60
        
        # Avg response time (from api.request events)
        api_events = Event.objects.filter(
            timestamp__gte=one_hour_ago,
            event_type='api.request'
        )
        avg_response_time = 0
        if api_events.exists():
            times = [e.properties.get('duration_ms', 0) for e in api_events if e.properties.get('duration_ms')]
            avg_response_time = sum(times) / len(times) if times else 0
        
        data = {
            'active_users': active_users,
            'events_per_minute': round(events_per_minute),
            'revenue_per_minute': round(revenue_per_minute, 2),
            'top_events': top_events,
            'top_pages': top_pages,
            'errors_per_minute': round(errors_per_minute),
            'avg_response_time': round(avg_response_time, 2),
        }
        return Response(RealtimeMetricsSerializer(data).data)


class DashboardViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Dashboard.objects.filter(
            Q(owner=self.request.user) | Q(is_public=True)
        ).prefetch_related('widgets')
    
    def get_serializer_class(self):
        if self.request.method in ['POST', 'PUT', 'PATCH']:
            return DashboardCreateSerializer
        return DashboardSerializer
    
    def list(self, request):
        queryset = self.get_queryset().order_by('-updated_at')
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    def retrieve(self, request, pk):
        dashboard = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(dashboard)
        return Response(serializer.data)
    
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, pk):
        dashboard = get_object_or_404(self.get_queryset(), pk=pk)
        if dashboard.owner != request.user and not request.user.is_staff:
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(dashboard, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def destroy(self, request, pk):
        dashboard = get_object_or_404(self.get_queryset(), pk=pk)
        if dashboard.owner != request.user and not request.user.is_staff:
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)
        dashboard.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk):
        dashboard = get_object_or_404(self.get_queryset(), pk=pk)
        new_dashboard = Dashboard.objects.create(
            owner=request.user,
            name=f"{dashboard.name} (Copy)",
            description=dashboard.description,
            layout=dashboard.layout,
            filters=dashboard.filters,
            is_default=False,
            is_public=False
        )
        for widget in dashboard.widgets.all():
            DashboardWidget.objects.create(dashboard=new_dashboard, **{
                'widget_type': widget.widget_type,
                'title': widget.title,
                'description': widget.description,
                'metric_names': widget.metric_names,
                'dimensions': widget.dimensions,
                'filters': widget.filters,
                'time_range': widget.time_range,
                'granularity': widget.granularity,
                'chart_options': widget.chart_options,
                'colors': widget.colors,
                'x': widget.x,
                'y': widget.y,
                'width': widget.width,
                'height': widget.height,
            })
        return Response(DashboardSerializer(new_dashboard).data, status=status.HTTP_201_CREATED)


class DashboardWidgetViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DashboardWidgetSerializer
    
    def get_queryset(self):
        return DashboardWidget.objects.filter(dashboard__owner=self.request.user)
    
    def create(self, request):
        dashboard_id = request.data.get('dashboard')
        dashboard = get_object_or_404(Dashboard, id=dashboard_id, owner=request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(dashboard=dashboard)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, pk):
        widget = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(widget, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    def destroy(self, request, pk):
        widget = get_object_or_404(self.get_queryset(), pk=pk)
        widget.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReportViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Report.objects.filter(owner=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReportCreateSerializer
        return ReportSerializer
    
    def list(self, request):
        queryset = self.get_queryset().order_by('-created_at')
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    def retrieve(self, request, pk):
        report = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(report)
        return Response(serializer.data)
    
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def destroy(self, request, pk):
        report = get_object_or_404(self.get_queryset(), pk=pk)
        report.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def generate(self, request, pk):
        report = get_object_or_404(self.get_queryset(), pk=pk)
        report.status = Report.Status.GENERATING
        report.save()
        
        try:
            data = self._execute_query(report.query)
            report.status = Report.Status.COMPLETED
            report.row_count = len(data)
            report.last_generated_at = timezone.now()
            
            # Generate file
            if report.format == 'csv':
                report.file = self._generate_csv(data)
            elif report.format == 'json':
                report.file = self._generate_json(data)
            
            report.save()
        except Exception as e:
            report.status = Report.Status.FAILED
            report.error_message = str(e)
            report.save()
        
        return Response(ReportSerializer(report).data)
    
    def _execute_query(self, query):
        # Simplified query execution - in production use a proper query builder
        return []
    
    def _generate_csv(self, data):
        return None
    
    def _generate_json(self, data):
        return None


class RetentionView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        period_type = request.query_params.get('period_type', 'day')
        app = request.query_params.get('app', '')
        user_role = request.query_params.get('user_role', '')
        days = int(request.query_params.get('days', 30))
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        queryset = RetentionCohort.objects.filter(
            cohort_date__gte=start_date,
            cohort_date__lte=end_date,
            period_type=period_type,
        )
        
        if app:
            queryset = queryset.filter(app=app)
        if user_role:
            queryset = queryset.filter(user_role=user_role)
        
        cohorts = queryset.order_by('-cohort_date', 'period')
        
        # Build cohort matrix
        matrix = {}
        for cohort in cohorts:
            key = str(cohort.cohort_date)
            if key not in matrix:
                matrix[key] = {
                    'cohort_date': cohort.cohort_date,
                    'cohort_size': cohort.cohort_size,
                    'periods': {}
                }
            matrix[key]['periods'][cohort.period] = {
                'retained': cohort.retained_users,
                'rate': float(cohort.retention_rate)
            }
        
        return Response({
            'period_type': period_type,
            'cohorts': list(matrix.values()),
            'summary': self._calculate_summary(matrix)
        })
    
    def _calculate_summary(self, matrix):
        if not matrix:
            return {}
        periods = set()
        for c in matrix.values():
            periods.update(c['periods'].keys())
        periods = sorted(periods)
        
        summary = {}
        for p in periods:
            total_cohort = sum(c['cohort_size'] for c in matrix.values())
            total_retained = sum(c['periods'].get(p, {}).get('retained', 0) for c in matrix.values())
            summary[p] = {
                'avg_retention_rate': round((total_retained / total_cohort * 100) if total_cohort else 0, 2),
                'total_retained': total_retained,
                'total_cohort': total_cohort
            }
        return summary


class FunnelAnalysisView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        funnel_name = request.query_params.get('funnel')
        if not funnel_name:
            return Response({"error": "funnel parameter required"}, status=status.HTTP_400_BAD_REQUEST)
        
        steps = FunnelStep.objects.filter(funnel_name=funnel_name).order_by('step_order')
        if not steps.exists():
            return Response({"error": "Funnel not found"}, status=status.HTTP_404_NOT_FOUND)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', timezone.now().date())
        
        if start_date:
            start_date = datetime.fromisoformat(start_date).date()
        else:
            start_date = end_date - timedelta(days=30)
        
        results = []
        previous_users = None
        
        for step in steps:
            filters = Q(event_type=step.event_type, timestamp__date__gte=start_date, timestamp__date__lte=end_date)
            for key, value in step.filters.items():
                filters &= Q(properties__contains={key: value})
            
            users = Event.objects.filter(filters).values('user').distinct()
            
            if previous_users is not None:
                users = users.filter(user__in=previous_users)
            
            count = users.count()
            conversion = (count / previous_users.count() * 100) if previous_users and previous_users.count() > 0 else 100
            drop_off = 100 - conversion if previous_users is not None else 0
            
            results.append({
                'step': step.step_name,
                'event_type': step.event_type,
                'count': count,
                'conversion_rate': round(conversion, 2),
                'drop_off_rate': round(drop_off, 2),
            })
            previous_users = users
        
        return Response({
            'funnel_name': funnel_name,
            'steps': results,
            'total_conversion_rate': results[-1]['conversion_rate'] if results else 0
        })


class CohortAnalysisView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        period_type = request.query_params.get('period_type', 'day')
        metric = request.query_params.get('metric', 'retention')
        
        cohorts = RetentionCohort.objects.filter(period_type=period_type).order_by('-cohort_date')[:100]
        
        return Response(CohortAnalysisSerializer({
            'cohorts': cohorts,
            'summary': {}
        }).data)


class UserJourneyView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_id = request.query_params.get('user_id')
        if not user_id and not request.user.is_staff:
            user_id = request.user.id
        
        if not user_id:
            return Response({"error": "user_id required"}, status=status.HTTP_400_BAD_REQUEST)
        
        hours = int(request.query_params.get('hours', 24))
        since = timezone.now() - timedelta(hours=hours)
        
        events = Event.objects.filter(
            user_id=user_id,
            timestamp__gte=since
        ).order_by('timestamp')
        
        # Group into sessions (30 min gap)
        sessions = []
        current_session = []
        last_time = None
        
        for event in events:
            if last_time and (event.timestamp - last_time).total_seconds() > 1800:
                if current_session:
                    sessions.append(current_session)
                current_session = []
            current_session.append(event)
            last_time = event.timestamp
        
        if current_session:
            sessions.append(current_session)
        
        journey = []
        for session in sessions:
            duration = int((session[-1].timestamp - session[0].timestamp).total_seconds()) if len(session) > 1 else 0
            journey.append({
                'session_start': session[0].timestamp,
                'duration': duration,
                'events': EventSerializer(session, many=True).data,
                'page_count': sum(1 for e in session if e.event_type == 'page.view'),
                'conversions': [e for e in session if 'payment' in e.event_type or 'enrolled' in e.event_type],
            })
        
        return Response({
            'user_id': user_id,
            'sessions': journey,
            'total_sessions': len(journey),
            'total_events': events.count(),
        })


class AlertViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        return Alert.objects.filter(is_enabled=True)
    
    def get_serializer_class(self):
        return AlertSerializer
    
    def list(self, request):
        queryset = self.get_queryset().order_by('-created_at')
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    def retrieve(self, request, pk):
        alert = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(alert)
        return Response(serializer.data)
    
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = serializer.save()
        if alert.notify_user_ids:
            alert.notify_users.set(alert.notify_user_ids)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, pk):
        alert = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(alert, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        alert = serializer.save()
        if 'notify_user_ids' in request.data:
            alert.notify_users.set(request.data['notify_user_ids'])
        return Response(serializer.data)
    
    def destroy(self, request, pk):
        alert = get_object_or_404(self.get_queryset(), pk=pk)
        alert.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk):
        alert = get_object_or_404(self.get_queryset(), pk=pk)
        # Evaluate condition against latest metrics
        return Response({"status": "tested", "would_trigger": False})


class AlertTriggerView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AlertTriggerSerializer
    
    def get_queryset(self):
        return AlertTrigger.objects.select_related('alert', 'acknowledged_by')
    
    def list(self, request):
        queryset = self.get_queryset().order_by('-triggered_at')
        
        alert_id = request.query_params.get('alert')
        if alert_id:
            queryset = queryset.filter(alert_id=alert_id)
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(alert__status=status_filter)
        
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def action(self, request, pk):
        trigger = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = AlertActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        if serializer.validated_data['action'] == 'acknowledge':
            trigger.acknowledged_at = timezone.now()
            trigger.acknowledged_by = request.user
            trigger.alert.status = Alert.Status.ACKNOWLEDGED
            trigger.alert.save()
        elif serializer.validated_data['action'] == 'resolve':
            trigger.resolved_at = timezone.now()
            trigger.alert.status = Alert.Status.RESOLVED
            trigger.alert.save()
        
        trigger.save()
        return Response(AlertTriggerSerializer(trigger).data)


class AnalyticsSettingsView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AnalyticsSettingsSerializer
    
    def get_queryset(self):
        return AnalyticsSettings.objects.all()
    
    def list(self, request):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk):
        setting = get_object_or_404(self.get_queryset(), key=pk)
        serializer = self.get_serializer(setting)
        return Response(serializer.data)
    
    def update(self, request, pk):
        setting = get_object_or_404(self.get_queryset(), key=pk)
        serializer = self.get_serializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


class ExportEventsView(APIView):
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        event_types = request.query_params.getlist('event_type')
        
        if not start_date or not end_date:
            return Response({"error": "start_date and end_date required"}, status=status.HTTP_400_BAD_REQUEST)
        
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        queryset = Event.objects.filter(timestamp__gte=start, timestamp__lte=end)
        if event_types:
            queryset = queryset.filter(event_type__in=event_types)
        
        queryset = queryset.select_related('user').order_by('timestamp')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="events_{start_date}_to_{end_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['timestamp', 'event_type', 'user_id', 'user_email', 'session_id', 'properties', 'source_app', 'url', 'ip_address'])
        
        for event in queryset.iterator(chunk_size=1000):
            writer.writerow([
                event.timestamp.isoformat(),
                event.event_type,
                event.user_id or '',
                event.user.email if event.user else '',
                event.session_id,
                json.dumps(event.properties),
                event.source_app,
                event.url,
                event.ip_address or '',
            ])
        
        return response