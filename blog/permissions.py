from rest_framework import permissions
from .models import Post, Comment


class IsAuthorOrStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        if isinstance(obj, Post):
            return obj.author == request.user
        if isinstance(obj, Comment):
            return obj.author == request.user or obj.post.author == request.user
        return False


class IsCommentAuthorOrPostAuthorOrStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        if isinstance(obj, Comment):
            return obj.author == request.user or obj.post.author == request.user
        return False