from rest_framework import permissions
from .models import ThreadParticipant, Thread


class IsThreadParticipant(permissions.BasePermission):
    """Object-level permission to ensure the requesting user is an active participant of the thread."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        thread_id = view.kwargs.get('thread_id') or view.kwargs.get('pk')
        if not thread_id:
            return True
        return ThreadParticipant.objects.filter(
            thread_id=thread_id,
            user=request.user,
            is_active=True
        ).exists()

    def has_object_permission(self, request, view, obj):
        thread_id = obj.thread_id if hasattr(obj, 'thread_id') else obj.id
        return ThreadParticipant.objects.filter(
            thread_id=thread_id,
            user=request.user,
            is_active=True
        ).exists()


class IsThreadAdmin(permissions.BasePermission):
    """Permission to check if user is admin/owner of the thread."""

    def has_object_permission(self, request, view, obj):
        thread = obj if isinstance(obj, Thread) else obj.thread
        participant = thread.participants.filter(user=request.user, is_active=True).first()
        return participant and participant.role in [ThreadParticipant.Role.ADMIN, ThreadParticipant.Role.OWNER]


class IsMessageSender(permissions.BasePermission):
    """Permission to ensure only the author of a message can edit/delete it."""

    def has_object_permission(self, request, view, obj):
        return obj.sender == request.user


class IsInviteRecipient(permissions.BasePermission):
    """Permission for invite responses - only the invited user can accept/decline."""

    def has_object_permission(self, request, view, obj):
        return obj.invited_user == request.user