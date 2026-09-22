from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TeacherEarningView, EarningsSummaryView,
    TransactionListView, TransactionDetailView,
    PayoutListView, PayoutDetailView, PayoutRequestView,
    PayoutScheduleView,
    RevenueReportListView, RevenueReportDetailView, RevenueReportGenerateView,
    AdminEarningsOverviewView, AdminPayoutManagementView, AdminPayoutActionView
)

urlpatterns = [
    path('me/', TeacherEarningView.as_view(), name='teacher-earning'),
    path('summary/', EarningsSummaryView.as_view(), name='earnings-summary'),

    path('transactions/', TransactionListView.as_view(), name='transaction-list'),
    path('transactions/<uuid:pk>/', TransactionDetailView.as_view(), name='transaction-detail'),

    path('payouts/', PayoutListView.as_view(), name='payout-list'),
    path('payouts/<uuid:pk>/', PayoutDetailView.as_view(), name='payout-detail'),
    path('payouts/request/', PayoutRequestView.as_view(), name='payout-request'),

    path('payout-schedule/', PayoutScheduleView.as_view(), name='payout-schedule'),

    path('reports/', RevenueReportListView.as_view(), name='revenue-report-list'),
    path('reports/generate/', RevenueReportGenerateView.as_view(), name='revenue-report-generate'),
    path('reports/<uuid:pk>/', RevenueReportDetailView.as_view(), name='revenue-report-detail'),

    # Admin
    path('admin/overview/', AdminEarningsOverviewView.as_view(), name='admin-earnings-overview'),
    path('admin/payouts/', AdminPayoutManagementView.as_view(), name='admin-payout-list'),
    path('admin/payouts/<uuid:pk>/action/', AdminPayoutActionView.as_view(), name='admin-payout-action'),
]