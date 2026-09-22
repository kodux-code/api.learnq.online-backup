from django.contrib import admin

from .models import (
    QuestionBank, Assessment, AssessmentQuestion,
    Attempt, Answer, Rubric, RubricCriterion, RubricLevel, RubricScore,
    PeerReview
)


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ['title', 'question_type', 'difficulty', 'creator', 'course', 'is_public', 'usage_count', 'created_at']
    list_filter = ['question_type', 'difficulty', 'is_public', 'course', 'created_at']
    search_fields = ['title', 'content', 'creator__display_name', 'tags']
    raw_id_fields = ['creator', 'course']
    readonly_fields = ['usage_count', 'avg_difficulty_rating', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 50


class AssessmentQuestionInline(admin.TabularInline):
    model = AssessmentQuestion
    extra = 0
    raw_id_fields = ['question']
    ordering = ['order']


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'assessment_type', 'course', 'status', 'grading_type', 'total_points', 'max_attempts', 'passing_score', 'published_at']
    list_filter = ['assessment_type', 'status', 'grading_type', 'course', 'created_at', 'published_at']
    search_fields = ['title', 'description', 'course__title', 'created_by__display_name']
    raw_id_fields = ['course', 'section', 'lecture', 'created_by']
    filter_horizontal = ['prerequisite_assessments']
    readonly_fields = ['total_points', 'created_at', 'updated_at', 'published_at']
    ordering = ['-created_at']
    list_per_page = 25
    inlines = [AssessmentQuestionInline]

    fieldsets = (
        (None, {'fields': ('title', 'slug', 'description', 'instructions')}),
        ('Type & Grading', {'fields': ('assessment_type', 'grading_type', 'status')}),
        ('Course', {'fields': ('course', 'section', 'lecture')}),
        ('Timing', {'fields': ('time_limit', 'available_from', 'available_until', 'allow_late_submission', 'late_penalty_percent')}),
        ('Attempts', {'fields': ('max_attempts', 'passing_score')}),
        ('Display', {'fields': ('show_correct_answers', 'show_explanations', 'show_score_immediately', 'allow_review', 'randomize_questions', 'randomize_options', 'questions_per_attempt')}),
        ('Proctoring', {'fields': ('require_proctoring', 'proctoring_settings')}),
        ('Prerequisites', {'fields': ('prerequisite_assessments',)}),
        ('Meta', {'fields': ('created_by', 'total_points', 'created_at', 'updated_at', 'published_at')}),
    )


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'assessment', 'student', 'attempt_number', 'status', 'score_percentage', 'is_passed', 'started_at', 'submitted_at']
    list_filter = ['status', 'is_passed', 'assessment__course', 'started_at', 'submitted_at']
    search_fields = ['student__display_name', 'student__email', 'assessment__title']
    raw_id_fields = ['assessment', 'student', 'enrollment', 'graded_by']
    readonly_fields = ['started_at', 'submitted_at', 'graded_at', 'earned_points', 'total_points', 'score_percentage', 'is_passed', 'created_at', 'updated_at']
    ordering = ['-started_at']
    list_per_page = 50


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'question', 'is_correct', 'points_earned', 'max_points', 'auto_graded', 'created_at']
    list_filter = ['is_correct', 'auto_graded', 'question__question_type', 'created_at']
    search_fields = ['attempt__student__display_name', 'question__title', 'response_text']
    raw_id_fields = ['attempt', 'question', 'assessment_question', 'graded_by']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 100


class RubricLevelInline(admin.TabularInline):
    model = RubricLevel
    extra = 0
    ordering = ['order']


class RubricCriterionInline(admin.TabularInline):
    model = RubricCriterion
    extra = 0
    ordering = ['order']
    inlines = [RubricLevelInline]


@admin.register(Rubric)
class RubricAdmin(admin.ModelAdmin):
    list_display = ['name', 'assessment', 'total_points', 'created_at']
    search_fields = ['name', 'assessment__title']
    raw_id_fields = ['assessment']
    inlines = [RubricCriterionInline]
    readonly_fields = ['created_at', 'updated_at']


@admin.register(RubricScore)
class RubricScoreAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'criterion', 'level', 'points_earned', 'graded_by', 'graded_at']
    list_filter = ['criterion__rubric__assessment', 'graded_at']
    raw_id_fields = ['attempt', 'criterion', 'level', 'graded_by']
    readonly_fields = ['graded_at']


@admin.register(PeerReview)
class PeerReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'assessment', 'submission', 'reviewer', 'status', 'score_given', 'assigned_at', 'submitted_at']
    list_filter = ['status', 'assessment__course', 'assigned_at']
    search_fields = ['reviewer__display_name', 'submission__student__display_name']
    raw_id_fields = ['assessment', 'submission', 'reviewer']
    readonly_fields = ['assigned_at', 'created_at', 'updated_at']
    ordering = ['-assigned_at']
