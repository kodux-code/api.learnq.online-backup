from django.contrib import admin
from .models import Category, Tag, Post, Comment, PostLike, CommentLike, PostView, Newsletter, NewsletterCampaign


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'color', 'order', 'is_active', 'posts_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['order', 'name']

    def posts_count(self, obj):
        return obj.posts.count()
    posts_count.short_description = 'Posts'


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'color', 'posts_count', 'created_at']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['name']

    def posts_count(self, obj):
        return obj.posts.count()
    posts_count.short_description = 'Posts'


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'category', 'status', 'visibility', 'is_featured', 'view_count', 'like_count', 'comment_count', 'published_at']
    list_filter = ['status', 'visibility', 'is_featured', 'category', 'tags', 'allow_comments', 'created_at', 'published_at']
    search_fields = ['title', 'excerpt', 'content', 'author__display_name', 'author__email']
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ['author']
    filter_horizontal = ['tags']
    readonly_fields = ['view_count', 'like_count', 'comment_count', 'reading_time', 'published_at', 'created_at', 'updated_at']
    ordering = ['-published_at', '-created_at']
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('title', 'slug', 'excerpt', 'content', 'content_html')}),
        ('Organization', {'fields': ('author', 'category', 'tags')}),
        ('Publishing', {'fields': ('status', 'visibility', 'is_featured', 'allow_comments', 'scheduled_at', 'published_at')}),
        ('Media', {'fields': ('featured_image', 'featured_image_alt')}),
        ('SEO', {'fields': ('meta_title', 'meta_description', 'canonical_url'), 'classes': ('collapse',)}),
        ('Stats', {'fields': ('view_count', 'like_count', 'comment_count', 'reading_time'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('author', 'category').prefetch_related('tags')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['post', 'author', 'parent', 'is_approved', 'is_pinned', 'like_count', 'created_at']
    list_filter = ['is_approved', 'is_pinned', 'created_at']
    search_fields = ['content', 'author__display_name', 'post__title']
    raw_id_fields = ['post', 'author', 'parent']
    readonly_fields = ['like_count', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 50

    actions = ['approve_comments', 'unapprove_comments']

    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
    approve_comments.short_description = "Approve selected comments"

    def unapprove_comments(self, request, queryset):
        queryset.update(is_approved=False)
    unapprove_comments.short_description = "Unapprove selected comments"


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ['post', 'user', 'created_at']
    list_filter = ['created_at']
    raw_id_fields = ['post', 'user']
    ordering = ['-created_at']


@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):
    list_display = ['comment', 'user', 'created_at']
    list_filter = ['created_at']
    raw_id_fields = ['comment', 'user']
    ordering = ['-created_at']


@admin.register(PostView)
class PostViewAdmin(admin.ModelAdmin):
    list_display = ['post', 'user', 'session_key', 'ip_address', 'viewed_at']
    list_filter = ['viewed_at']
    raw_id_fields = ['post', 'user']
    readonly_fields = ['post', 'user', 'session_key', 'ip_address', 'user_agent', 'referrer', 'viewed_at']
    ordering = ['-viewed_at']
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    list_display = ['email', 'name', 'is_active', 'source', 'subscribed_at', 'unsubscribed_at']
    list_filter = ['is_active', 'source', 'subscribed_at']
    search_fields = ['email', 'name']
    readonly_fields = ['subscribed_at', 'unsubscribed_at']
    ordering = ['-subscribed_at']
    list_per_page = 50


@admin.register(NewsletterCampaign)
class NewsletterCampaignAdmin(admin.ModelAdmin):
    list_display = ['subject', 'status', 'scheduled_at', 'sent_at', 'recipient_count', 'open_count', 'click_count', 'created_at']
    list_filter = ['status', 'created_at', 'sent_at']
    search_fields = ['subject', 'preheader']
    readonly_fields = ['recipient_count', 'open_count', 'click_count', 'sent_at', 'created_at', 'updated_at']
    ordering = ['-created_at']
    list_per_page = 25

    fieldsets = (
        (None, {'fields': ('subject', 'preheader', 'content', 'content_html')}),
        ('Scheduling', {'fields': ('status', 'scheduled_at', 'sent_at')}),
        ('Stats', {'fields': ('recipient_count', 'open_count', 'click_count'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )