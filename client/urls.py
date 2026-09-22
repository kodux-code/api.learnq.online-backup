from django.urls import path
from .views import (
    PublicUserProfileView, ToggleFollowView, FollowersListView, FollowingListView,
    ClientRegisterView, ClientVerifyEmailView,
    ClientListView, ClientDetailView, ClientHardDeleteView
)

urlpatterns = [
    path('register/', ClientRegisterView.as_view(), name='register'),
    path('verify-email/', ClientVerifyEmailView.as_view(), name='verify-email'),
    path('users/', ClientListView.as_view(), name='client-list'),
    path('users/<uuid:pk>/', ClientDetailView.as_view(), name='client-detail'),
    path('users/<uuid:pk>/hard-delete/', ClientHardDeleteView.as_view(), name='client-hard-delete'),
    path('profile/<uuid:id>/', PublicUserProfileView.as_view(), name='public-profile'),
    path('profile/<uuid:id>/follow/', ToggleFollowView.as_view(), name='toggle-follow'),
    path('profile/<uuid:id>/followers/', FollowersListView.as_view(), name='followers-list'),
    path('profile/<uuid:id>/following/', FollowingListView.as_view(), name='following-list'),
]