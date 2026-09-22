from rest_framework import permissions
from .models import Course, Enrollment


class IsTeacherOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if isinstance(obj, Course):
            return obj.course_teachers.filter(teacher=request.user, is_active=True).exists()
        if hasattr(obj, 'course'):
            return obj.course.course_teachers.filter(teacher=request.user, is_active=True).exists()
        if hasattr(obj, 'section'):
            return obj.section.course.course_teachers.filter(teacher=request.user, is_active=True).exists()
        return False


class IsEnrolledOrTeacher(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        course = obj.course if hasattr(obj, 'course') else obj
        if course.course_teachers.filter(teacher=request.user, is_active=True).exists():
            return True
        return Enrollment.objects.filter(
            student=request.user, course=course, status=Enrollment.Status.ACTIVE
        ).exists()


class IsStudentOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.student == request.user


class IsCoursePublished(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        course = obj if isinstance(obj, Course) else obj.course
        if course.status == Course.Status.PUBLISHED:
            return True
        if request.user.is_staff:
            return True
        return course.course_teachers.filter(teacher=request.user, is_active=True).exists()


class CanManageEnrollment(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.student == request.user or obj.course.course_teachers.filter(
            teacher=request.user, is_active=True
        ).exists()