from django.contrib import admin
from .models import StudentAccount, TeacherAccount, ModeratorAccount


@admin.register(StudentAccount)
class StudentAccountAdmin(admin.ModelAdmin):
    list_display = ['client', 'grade_level', 'gpa', 'credits_earned', 'notification_email', 'notification_push', 'preferred_language', 'created_at']
    list_filter = ['grade_level', 'notification_email', 'notification_push', 'preferred_language', 'created_at']
    search_fields = ['client__display_name', 'client__email', 'parent_email']
    raw_id_fields = ['client']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('client',)}),
        ('Academic Info', {'fields': ('grade_level', 'parent_email', 'date_of_birth', 'gpa', 'credits_earned')}),
        ('Notifications', {'fields': ('notification_email', 'notification_push', 'preferred_language')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(TeacherAccount)
class TeacherAccountAdmin(admin.ModelAdmin):
    list_display = ['client', 'rating', 'review_count', 'total_students', 'total_courses', 'hourly_rate', 'currency', 'auto_payout', 'payout_schedule', 'created_at']
    list_filter = ['currency', 'auto_payout', 'payout_schedule', 'created_at']
    search_fields = ['client__display_name', 'client__email', 'stripe_account_id', 'tax_id']
    raw_id_fields = ['client']
    readonly_fields = ['total_students', 'total_courses', 'rating', 'review_count', 'created_at', 'updated_at']
    ordering = ['-rating', '-created_at']
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('client',)}),
        ('Profile', {'fields': ('bio', 'qualifications')}),
        ('Pricing', {'fields': ('hourly_rate', 'currency')}),
        ('Stripe', {'fields': ('stripe_account_id', 'tax_id')}),
        ('Stats', {'fields': ('total_students', 'total_courses', 'rating', 'review_count'), 'classes': ('collapse',)}),
        ('Payout Settings', {'fields': ('auto_payout', 'payout_schedule')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    actions = ['update_teacher_stats']

    def update_teacher_stats(self, request, queryset):
        from course.models import Course, Enrollment, CourseTeacher
        from django.db.models import Count, Avg
        
        for teacher_account in queryset:
            teacher = teacher_account.client
            # Update course count
            teacher_account.total_courses = Course.objects.filter(
                course_teachers__teacher=teacher,
                course_teachers__is_active=True
            ).count()
            
            # Update student count
            teacher_account.total_students = Enrollment.objects.filter(
                course__course_teachers__teacher=teacher,
                course__course_teachers__is_active=True,
                status=Enrollment.Status.ACTIVE
            ).distinct().count()
            
            # Update rating
            from course.models import Review
            avg_rating = Review.objects.filter(
                enrollment__course__course_teachers__teacher=teacher,
                enrollment__course__course_teachers__is_active=True
            ).aggregate(avg=Avg('rating'))['avg']
            
            teacher_account.rating = round(float(avg_rating), 2) if avg_rating else 0
            teacher_account.review_count = Review.objects.filter(
                enrollment__course__course_teachers__teacher=teacher,
                enrollment__course__course_teachers__is_active=True
            ).count()
            
            teacher_account.save(update_fields=['total_courses', 'total_students', 'rating', 'review_count', 'updated_at'])
        
        self.message_user(request, f'Updated stats for {queryset.count()} teachers.')
    update_teacher_stats.short_description = "Update teacher stats (courses, students, rating)"


@admin.register(ModeratorAccount)
class ModeratorAccountAdmin(admin.ModelAdmin):
    list_display = ['client', 'department', 'is_senior', 'actions_taken', 'last_action_at', 'created_at']
    list_filter = ['department', 'is_senior', 'created_at']
    search_fields = ['client__display_name', 'client__email', 'department']
    raw_id_fields = ['client']
    readonly_fields = ['actions_taken', 'last_action_at', 'created_at', 'updated_at']
    ordering = ['-is_senior', '-created_at']
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('client',)}),
        ('Permissions', {'fields': ('permissions', 'department', 'is_senior')}),
        ('Activity', {'fields': ('actions_taken', 'last_action_at'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    actions = ['promote_to_senior', 'demote_from_senior']

    def promote_to_senior(self, request, queryset):
        queryset.update(is_senior=True)
        self.message_user(request, f'Promoted {queryset.count()} moderators to senior.')
    promote_to_senior.short_description = "Promote selected moderators to senior"

    def demote_from_senior(self, request, queryset):
        queryset.update(is_senior=False)
        self.message_user(request, f'Demoted {queryset.count()} moderators from senior.')
    demote_from_senior.short_description = "Demote selected moderators from senior"