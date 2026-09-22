from django.urls import path
from .views import (
    OrderViewSet, OrderWebhookView,
    BundleViewSet, CouponViewSet,
    SubscriptionPlanViewSet, SubscriptionViewSet,
    RefundViewSet, AdminRefundViewSet,
    PaymentStatsView
)

urlpatterns = [
    # Orders
    path('orders/', OrderViewSet.as_view(), name='order-list'),
    path('orders/preview/', OrderViewSet.as_view(), name='order-preview'),
    path('orders/<uuid:pk>/', OrderViewSet.as_view(), name='order-detail'),
    path('orders/<uuid:pk>/cancel/', OrderViewSet.as_view(), name='order-cancel'),

    # Webhooks
    path('webhooks/<str:gateway>/', OrderWebhookView.as_view(), name='payment-webhook'),

    # Bundles
    path('bundles/', BundleViewSet.as_view(), name='bundle-list'),
    path('bundles/<uuid:pk>/', BundleViewSet.as_view(), name='bundle-detail'),

    # Coupons
    path('coupons/', CouponViewSet.as_view(), name='coupon-list'),
    path('coupons/<uuid:pk>/', CouponViewSet.as_view(), name='coupon-detail'),
    path('coupons/validate/', CouponViewSet.as_view(), name='coupon-validate'),

    # Subscription Plans
    path('subscription-plans/', SubscriptionPlanViewSet.as_view(), name='subscription-plan-list'),
    path('subscription-plans/<uuid:pk>/', SubscriptionPlanViewSet.as_view(), name='subscription-plan-detail'),

    # Subscriptions
    path('subscriptions/', SubscriptionViewSet.as_view(), name='subscription-list'),
    path('subscriptions/<uuid:pk>/', SubscriptionViewSet.as_view(), name='subscription-detail'),
    path('subscriptions/<uuid:pk>/cancel/', SubscriptionViewSet.as_view(), name='subscription-cancel'),
    path('subscriptions/<uuid:pk>/resume/', SubscriptionViewSet.as_view(), name='subscription-resume'),
    path('subscriptions/<uuid:pk>/invoices/', SubscriptionViewSet.as_view(), name='subscription-invoices'),

    # Refunds
    path('refunds/', RefundViewSet.as_view(), name='refund-list'),
    path('refunds/<uuid:pk>/', RefundViewSet.as_view(), name='refund-detail'),

    # Admin Refunds
    path('admin/refunds/', AdminRefundViewSet.as_view(), name='admin-refund-list'),
    path('admin/refunds/<uuid:pk>/action/', AdminRefundViewSet.as_view(), name='admin-refund-action'),

    # Stats (Admin)
    path('admin/stats/', PaymentStatsView.as_view(), name='payment-stats'),
]