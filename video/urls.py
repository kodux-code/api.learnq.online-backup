from django.urls import path

from . import views


app_name = "video"

urlpatterns = [
    path("threads/<uuid:thread_id>/join/", views.JoinThreadVideoView.as_view(), name="join-thread-video"),
    path("threads/<uuid:thread_id>/signal/", views.CallSignalView.as_view(), name="signal-thread-video"),
    path("push/subscribe/", views.SavePushSubscriptionView.as_view(), name="push-subscribe"),
]
