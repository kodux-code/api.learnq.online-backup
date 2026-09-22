from django.contrib import admin
from .models import Question, Answer, QuestionTag, Vote, QuestionShare, AnswerReport


@admin.register(QuestionTag)
class QuestionTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'color', 'question_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['question_count', 'created_at']
    ordering = ['name']


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    raw_id_fields = ['author']
    readonly_fields = ['created_at', 'updated_at', 'is_accepted', 'vote_score']
    fields = ['author', 'body', 'is_accepted', 'is_deleted', 'created_at']
    ordering = ['-is_accepted', 'created_at']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'is_open', 'is_pinned', 'is_deleted', 'vote_score', 'answer_count', 'share_count', 'created_at']
    list_filter = ['is_open', 'is_pinned', 'is_deleted', 'tags', 'created_at']
    search_fields = ['title', 'body', 'author__display_name', 'author__email']
    raw_id_fields = ['author']
    filter_horizontal = ['tags']
    readonly_fields = ['created_at', 'updated_at', 'closed_at', 'vote_score', 'answer_count', 'share_count']
    ordering = ['-is_pinned', '-created_at']
    list_per_page = 25
    date_hierarchy = 'created_at'
    inlines = [AnswerInline]

    fieldsets = (
        (None, {'fields': ('author', 'title', 'body', 'tags')}),
        ('Status', {'fields': ('is_open', 'is_pinned', 'is_deleted')}),
        ('Stats', {'fields': ('vote_score', 'answer_count', 'share_count'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'closed_at'), 'classes': ('collapse',)}),
    )

    actions = ['close_questions', 'reopen_questions', 'pin_questions', 'unpin_questions', 'soft_delete_questions']

    def close_questions(self, request, queryset):
        for q in queryset.filter(is_open=True):
            q.close()
    close_questions.short_description = "Close selected questions"

    def reopen_questions(self, request, queryset):
        for q in queryset.filter(is_open=False):
            q.reopen()
    reopen_questions.short_description = "Reopen selected questions"

    def pin_questions(self, request, queryset):
        queryset.update(is_pinned=True)
    pin_questions.short_description = "Pin selected questions"

    def unpin_questions(self, request, queryset):
        queryset.update(is_pinned=False)
    unpin_questions.short_description = "Unpin selected questions"

    def soft_delete_questions(self, request, queryset):
        for q in queryset.filter(is_deleted=False):
            q.soft_delete()
    soft_delete_questions.short_description = "Soft delete selected questions"


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['id', 'question', 'author', 'is_accepted', 'is_deleted', 'vote_score', 'reply_count', 'created_at']
    list_filter = ['is_accepted', 'is_deleted', 'question__is_open', 'created_at']
    search_fields = ['body', 'author__display_name', 'author__email', 'question__title']
    raw_id_fields = ['question', 'author', 'parent']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at', 'vote_score', 'reply_count']
    ordering = ['-created_at']
    list_per_page = 50
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {'fields': ('question', 'parent', 'author', 'body')}),
        ('Status', {'fields': ('is_accepted', 'is_deleted')}),
        ('Stats', {'fields': ('vote_score', 'reply_count'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'deleted_at'), 'classes': ('collapse',)}),
    )

    actions = ['accept_answers', 'unaccept_answers', 'soft_delete_answers', 'restore_answers']

    def accept_answers(self, request, queryset):
        for a in queryset.filter(is_accepted=False):
            a.accept()
    accept_answers.short_description = "Accept selected answers"

    def unaccept_answers(self, request, queryset):
        for a in queryset.filter(is_accepted=True):
            a.unaccept()
    unaccept_answers.short_description = "Unaccept selected answers"

    def soft_delete_answers(self, request, queryset):
        for a in queryset.filter(is_deleted=False):
            a.soft_delete()
    soft_delete_answers.short_description = "Soft delete selected answers"

    def restore_answers(self, request, queryset):
        for a in queryset.filter(is_deleted=True):
            a.restore()
    restore_answers.short_description = "Restore selected answers"


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ['voter', 'question', 'answer', 'value', 'created_at']
    list_filter = ['value', 'created_at']
    search_fields = ['voter__display_name', 'voter__email', 'question__title']
    raw_id_fields = ['voter', 'question', 'answer']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 100
    date_hierarchy = 'created_at'


@admin.register(QuestionShare)
class QuestionShareAdmin(admin.ModelAdmin):
    list_display = ['question', 'shared_by', 'channel', 'created_at']
    list_filter = ['channel', 'created_at']
    search_fields = ['question__title', 'shared_by__display_name']
    raw_id_fields = ['question', 'shared_by']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    list_per_page = 50


@admin.register(AnswerReport)
class AnswerReportAdmin(admin.ModelAdmin):
    list_display = ['answer', 'reporter', 'reason', 'is_resolved', 'created_at']
    list_filter = ['reason', 'is_resolved', 'created_at']
    search_fields = ['answer__body', 'reporter__display_name', 'details']
    raw_id_fields = ['answer', 'reporter', 'resolved_by']
    readonly_fields = ['created_at', 'resolved_at']
    ordering = ['-created_at']
    list_per_page = 50

    actions = ['mark_resolved', 'dismiss']

    def mark_resolved(self, request, queryset):
        queryset.filter(is_resolved=False).update(
            is_resolved=True,
            resolved_by=request.user,
            resolved_at=timezone.now()
        )
    mark_resolved.short_description = "Mark selected reports as resolved"

    def dismiss(self, request, queryset):
        queryset.filter(is_resolved=False).update(
            is_resolved=True,
            resolved_by=request.user,
            resolved_at=timezone.now()
        )
    dismiss.short_description = "Dismiss selected reports"


from django.utils import timezone