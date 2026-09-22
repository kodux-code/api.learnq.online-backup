from django.urls import path
from .views import (
    GlobalUnreadCountView, ThreadListCreateView, ThreadDetailView,
    ThreadMarkReadView, ThreadLeaveView, MessageListCreateView,
    MessageDetailView, MessageReactionView, MessageReadReceiptView,
    ThreadInviteListCreateView, ThreadInviteResponseView,
    UserThreadSettingsView, UnreadCountDetailView
)

urlpatterns = [
    # Unread counts
    path('unread/', GlobalUnreadCountView.as_view(), name='global-unread-count'),
    path('unread/detail/', UnreadCountDetailView.as_view(), name='unread-count-detail'),

    # Threads (Inbox)
    path('', ThreadListCreateView.as_view(), name='thread-list-create'),
    path('<uuid:pk>/', ThreadDetailView.as_view(), name='thread-detail'),
    path('<uuid:pk>/read/', ThreadMarkReadView.as_view(), name='thread-mark-read'),
    path('<uuid:pk>/leave/', ThreadLeaveView.as_view(), name='thread-leave'),
    path('<uuid:pk>/settings/', UserThreadSettingsView.as_view(), name='thread-settings'),

    # Messages
    path('<uuid:thread_id>/messages/', MessageListCreateView.as_view(), name='message-list-create'),
    path('<uuid:thread_id>/messages/<uuid:pk>/', MessageDetailView.as_view(), name='message-detail'),
    path('<uuid:thread_id>/messages/<uuid:message_id>/reaction/', MessageReactionView.as_view(), name='message-reaction'),
    path('<uuid:thread_id>/messages/<uuid:message_id>/read/', MessageReadReceiptView.as_view(), name='message-read-receipt'),

    # Invites
    path('<uuid:thread_id>/invites/', ThreadInviteListCreateView.as_view(), name='thread-invite-list-create'),
    path('invites/<uuid:invite_id>/respond/', ThreadInviteResponseView.as_view(), name='thread-invite-respond'),
]