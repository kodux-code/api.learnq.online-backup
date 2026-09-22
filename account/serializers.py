from rest_framework import serializers
from django.db.models import Avg
from .models import StudentAccount, TeacherAccount, ModeratorAccount
from course.models import Course, Enrollment, Review


class StudentAccountSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(source='client.email', read_only=True)
    client_display_name = serializers.CharField(source='client.display_name', read_only=True)
    enrollments_count = serializers.SerializerMethodField()
    completed_courses_count = serializers.SerializerMethodField()
    in_progress_courses_count = serializers.SerializerMethodField()

    class Meta:
        model = StudentAccount
        fields = [
            'id', 'client', 'client_email', 'client_display_name',
            'grade_level', 'parent_email', 'date_of_birth',
            'gpa', 'credits_earned',
            'notification_email', 'notification_push', 'preferred_language',
            'enrollments_count', 'completed_courses_count', 'in_progress_courses_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'client', 'created_at', 'updated_at']

    def get_enrollments_count(self, obj):
        return Enrollment.objects.filter(student=obj.client).count()

    def get_completed_courses_count(self, obj):
        return Enrollment.objects.filter(student=obj.client, status=Enrollment.Status.COMPLETED).count()

    def get_in_progress_courses_count(self, obj):
        return Enrollment.objects.filter(student=obj.client, status=Enrollment.Status.ACTIVE).count()


class TeacherAccountSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(source='client.email', read_only=True)
    client_display_name = serializers.CharField(source='client.display_name', read_only=True)
    client_avatar = serializers.ImageField(source='client.avatar', read_only=True)
    courses_count = serializers.SerializerMethodField()
    total_students = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = TeacherAccount
        fields = [
            'id', 'client', 'client_email', 'client_display_name', 'client_avatar',
            'bio', 'qualifications',
            'hourly_rate', 'currency', 'stripe_account_id', 'tax_id',
            'total_students', 'total_courses', 'rating', 'review_count',
            'courses_count', 'average_rating',
            'auto_payout', 'payout_schedule',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'client', 'total_students', 'total_courses', 'rating', 'review_count', 'created_at', 'updated_at']

    def get_courses_count(self, obj):
        return Course.objects.filter(course_teachers__teacher=obj.client, course_teachers__is_active=True).count()

    def get_total_students(self, obj):
        return Enrollment.objects.filter(
            course__course_teachers__teacher=obj.client,
            course__course_teachers__is_active=True,
            status=Enrollment.Status.ACTIVE
        ).distinct().count()

    def get_average_rating(self, obj):
        avg = Review.objects.filter(
            enrollment__course__course_teachers__teacher=obj.client,
            enrollment__course__course_teachers__is_active=True
        ).aggregate(avg=Avg('rating'))['avg']
        return round(float(avg), 2) if avg else 0


class TeacherAccountPublicSerializer(serializers.ModelSerializer):
    client_display_name = serializers.CharField(source='client.display_name', read_only=True)
    client_avatar = serializers.ImageField(source='client.avatar', read_only=True)
    client_bio = serializers.CharField(source='client.bio', read_only=True)
    courses_count = serializers.SerializerMethodField()
    total_students = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = TeacherAccount
        fields = [
            'client_display_name', 'client_avatar', 'client_bio',
            'bio', 'qualifications',
            'rating', 'review_count',
            'courses_count', 'total_students', 'average_rating',
        ]

    def get_courses_count(self, obj):
        return Course.objects.filter(
            course_teachers__teacher=obj.client,
            course_teachers__is_active=True,
            status=Course.Status.PUBLISHED
        ).count()

    def get_total_students(self, obj):
        return Enrollment.objects.filter(
            course__course_teachers__teacher=obj.client,
            course__course_teachers__is_active=True,
            status=Enrollment.Status.ACTIVE
        ).distinct().count()

    def get_average_rating(self, obj):
        avg = Review.objects.filter(
            enrollment__course__course_teachers__teacher=obj.client,
            enrollment__course__course_teachers__is_active=True
        ).aggregate(avg=Avg('rating'))['avg']
        return round(float(avg), 2) if avg else 0


class TeacherAccountUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherAccount
        fields = [
            'bio', 'qualifications',
            'hourly_rate', 'currency', 'tax_id',
            'auto_payout', 'payout_schedule',
        ]


class ModeratorAccountSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(source='client.email', read_only=True)
    client_display_name = serializers.CharField(source='client.display_name', read_only=True)

    class Meta:
        model = ModeratorAccount
        fields = [
            'id', 'client', 'client_email', 'client_display_name',
            'permissions', 'department', 'is_senior',
            'actions_taken', 'last_action_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'client', 'actions_taken', 'last_action_at', 'created_at', 'updated_at']


class ModeratorAccountUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModeratorAccount
        fields = ['permissions', 'department', 'is_senior']