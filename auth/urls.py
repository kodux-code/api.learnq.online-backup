# auth/urls.py
from django.urls import path
from auth.views import (
    CurrentUserView, SecureLoginView, SecureTokenRefreshView, SecureLogoutView,
    PasswordResetRequestView, PasswordResetConfirmView,
    EmailVerifyView, ResendVerificationView
)

urlpatterns = [
    path('login/', SecureLoginView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', SecureTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', SecureLogoutView.as_view(), name='token_logout'),
    path("me/", CurrentUserView.as_view(), name="current_user"),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('verify-email/', EmailVerifyView.as_view(), name='verify_email'),
    path('resend-verification/', ResendVerificationView.as_view(), name='resend_verification'),
]
