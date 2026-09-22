from django.urls import path
from .views import (
    EventTrackView, BatchEventTrackView,
    TimeSeriesView, RealtimeMetricsView,
    DashboardViewSet, DashboardWidgetViewSet,
    ReportViewSet, RetentionView, FunnelAnalysisView,
    CohortAnalysisView, UserJourneyView,
    AlertViewSet, AlertTriggerView,
    AnalyticsSettingsView, ExportEventsView
)

urlpatterns = [
    # Event tracking
    path('events/track/', EventTrackView.as_view(), name='event-track'),
    path('events/batch/', BatchEventTrackView.as_view(), name='event-batch-track'),
    
    # Time series
    path('timeseries/', TimeSeriesView.as_view(), name='timeseries'),
    path('realtime/', RealtimeMetricsView.as_view(), name='realtime-metrics'),
    
    # Dashboards
    path('dashboards/', DashboardViewSet.as_view(), name='dashboard-list'),
    path('dashboards/<uuid:pk>/', DashboardViewSet.as_view(), name='dashboard-detail'),
    path('dashboards/<uuid:pk>/duplicate/', DashboardViewSet.as_view(), name='dashboard-duplicate'),
    
    # Widgets
    path('widgets/', DashboardWidgetViewSet.as_view(), name='widget-create'),
    path('widgets/<uuid:pk>/', DashboardWidgetViewSet.as_view(), name='widget-detail'),
    
    # Reports
    path('reports/', ReportViewSet.as_view(), name='report-list'),
    path('reports/<uuid:pk>/', ReportViewSet.as_view(), name='report-detail'),
    path('reports/<uuid:pk>/generate/', ReportViewSet.as_view(), name='report-generate'),
    
    # Retention
    path('retention/', RetentionView.as_view(), name='retention'),
    
    # Funnels
    path('funnels/', FunnelAnalysisView.as_view(), name='funnel-analysis'),
    
    # Cohorts
    path('cohorts/', CohortAnalysisView.as_view(), name='cohort-analysis'),
    
    # User Journey
    path('journey/', UserJourneyView.as_view(), name='user-journey'),
    
    # Alerts
    path('alerts/', AlertViewSet.as_view(), name='alert-list'),
    path('alerts/<uuid:pk>/', AlertViewSet.as_view(), name='alert-detail'),
    path('alerts/<uuid:pk>/test/', AlertViewSet.as_view(), name='alert-test'),
    
    # Alert Triggers
    path('alert-triggers/', AlertTriggerView.as_view(), name='alert-trigger-list'),
    path('alert-triggers/<uuid:pk>/action/', AlertTriggerView.as_view(), name='alert-trigger-action'),
    
    # Settings
    path('settings/', AnalyticsSettingsView.as_view(), name='analytics-settings'),
    path('settings/<str:pk>/', AnalyticsSettingsView.as_view(), name='analytics-setting-detail'),
    
    # Export
    path('export/events/', ExportEventsView.as_view(), name='export-events'),
]