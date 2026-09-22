from django.urls import path
from .views import (
    TransactionViewSet, WalletView, WalletTransactionListView,
    WalletTopUpView, TransactionStatsView, TeacherEarningsView
)

urlpatterns = [
    path('', TransactionViewSet.as_view(), name='transaction-list'),
    path('<uuid:pk>/', TransactionViewSet.as_view(), name='transaction-detail'),
    path('<uuid:pk>/complete/', TransactionViewSet.as_view(), name='transaction-complete'),
    path('<uuid:pk>/fail/', TransactionViewSet.as_view(), name='transaction-fail'),
    path('<uuid:pk>/reverse/', TransactionViewSet.as_view(), name='transaction-reverse'),
    path('my-earnings/', TransactionViewSet.as_view(), name='my-earnings'),
    path('my-purchases/', TransactionViewSet.as_view(), name='my-purchases'),
    
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('wallet/transactions/', WalletTransactionListView.as_view(), name='wallet-transactions'),
    path('wallet/topup/', WalletTopUpView.as_view(), name='wallet-topup'),
    
    path('stats/', TransactionStatsView.as_view(), name='transaction-stats'),
    path('teacher-earnings/', TeacherEarningsView.as_view(), name='teacher-earnings'),
]