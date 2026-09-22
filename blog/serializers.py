from rest_framework import serializers
from django.db.models import Count, Exists, OuterRef, Q
from .models import Category, Tag, Post, Comment, PostLike, CommentLike, Newsletter, NewsletterCampaign
from client.serializers import PublicProfileSerializer


class CategorySerializer(serializers.ModelSerializer):
    posts_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'color', 'icon', 'order', 'is_active', 'posts_count']

    def get_posts_count(self, obj):
        return obj.posts.filter(status=Post.Status.PUBLISHED, visibility=Post.Visibility.PUBLIC).count()


class TagSerializer(serializers.ModelSerializer):
    posts_count = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'color', 'posts_count']

    def get_posts_count(self, obj):
        return obj.posts.filter(status=Post.Status.PUBLISHED, visibility=Post.Visibility.PUBLIC).count()


class PostListSerializer(serializers.ModelSerializer):
    author = PublicProfileSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'title', 'slug', 'excerpt', 'author', 'category', 'tags',
            'status', 'visibility', 'featured_image', 'featured_image_alt',
            'view_count', 'like_count', 'comment_count', 'reading_time',
            'is_featured', 'published_at', 'created_at', 'updated_at',
            'is_liked', 'is_bookmarked'
        ]

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if hasattr(obj, 'liked_by_current_user'):
                return obj.liked_by_current_user
            return PostLike.objects.filter(post=obj, user=request.user).exists()
        return False

    def get_is_bookmarked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if hasattr(obj, 'bookmarked_by_current_user'):
                return obj.bookmarked_by_current_user
            return obj.bookmarks.filter(user=request.user).exists()
        return False


class PostDetailSerializer(PostListSerializer):
    content = serializers.CharField(read_only=True)
    content_html = serializers.CharField(read_only=True)
    meta_title = serializers.CharField(read_only=True)
    meta_description = serializers.CharField(read_only=True)
    canonical_url = serializers.CharField(read_only=True)
    allow_comments = serializers.BooleanField(read_only=True)
    next_post = serializers.SerializerMethodField()
    prev_post = serializers.SerializerMethodField()

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + [
            'content', 'content_html', 'meta_title', 'meta_description',
            'canonical_url', 'allow_comments', 'scheduled_at',
            'next_post', 'prev_post'
        ]

    def get_next_post(self, obj):
        next_post = Post.objects.filter(
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at__gt=obj.published_at
        ).order_by('published_at').first()
        if next_post:
            return {'id': next_post.id, 'title': next_post.title, 'slug': next_post.slug}
        return None

    def get_prev_post(self, obj):
        prev_post = Post.objects.filter(
            status=Post.Status.PUBLISHED,
            visibility=Post.Visibility.PUBLIC,
            published_at__lt=obj.published_at
        ).order_by('-published_at').first()
        if prev_post:
            return {'id': prev_post.id, 'title': prev_post.title, 'slug': prev_post.slug}
        return None


class PostCreateUpdateSerializer(serializers.ModelSerializer):
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        write_only=True
    )
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True
    )

    class Meta:
        model = Post
        fields = [
            'id', 'title', 'excerpt', 'content', 'category', 'tags', 'tag_ids',
            'status', 'visibility', 'featured_image', 'featured_image_alt',
            'meta_title', 'meta_description', 'canonical_url',
            'allow_comments', 'is_featured', 'scheduled_at'
        ]
        read_only_fields = ['id', 'slug', 'author', 'view_count', 'like_count',
                           'comment_count', 'reading_time', 'published_at',
                           'created_at', 'updated_at']

    def validate_tags(self, value):
        existing_tags = Tag.objects.filter(slug__in=[slugify(t) for t in value])
        existing_slugs = set(existing_tags.values_list('slug', flat=True))
        return value

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', [])
        tag_ids = validated_data.pop('tag_ids', [])
        validated_data['author'] = self.context['request'].user
        post = Post.objects.create(**validated_data)
        self._set_tags(post, tags_data, tag_ids)
        return post

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        tag_ids = validated_data.pop('tag_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tags_data is not None or tag_ids is not None:
            self._set_tags(instance, tags_data or [], tag_ids or [])
        return instance

    def _set_tags(self, post, tags_data, tag_ids):
        tags = []
        if tag_ids:
            tags.extend(Tag.objects.filter(id__in=tag_ids))
        for tag_name in tags_data:
            slug = slugify(tag_name)
            tag, _ = Tag.objects.get_or_create(slug=slug, defaults={'name': tag_name, 'color': '#64748b'})
            tags.append(tag)
        post.tags.set(tags)


class CommentSerializer(serializers.ModelSerializer):
    author = PublicProfileSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'post', 'author', 'parent', 'content', 'content_html',
            'is_approved', 'is_pinned', 'like_count',
            'replies', 'reply_count', 'is_liked',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'post', 'author', 'like_count', 'created_at', 'updated_at']

    def get_replies(self, obj):
        if obj.replies.exists():
            return CommentSerializer(obj.replies.filter(is_approved=True), many=True, context=self.context).data
        return []

    def get_reply_count(self, obj):
        return obj.replies.filter(is_approved=True).count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return CommentLike.objects.filter(comment=obj, user=request.user).exists()
        return False


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['post', 'parent', 'content']

    def validate(self, attrs):
        post = attrs.get('post')
        parent = attrs.get('parent')
        if parent and parent.post != post:
            raise serializers.ValidationError("Parent comment must belong to the same post.")
        if not post.allow_comments:
            raise serializers.ValidationError("Comments are disabled for this post.")
        return attrs

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class PostLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostLike
        fields = ['id', 'post', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class CommentLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentLike
        fields = ['id', 'comment', 'user', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class NewsletterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Newsletter
        fields = ['id', 'email', 'name', 'is_active', 'source', 'subscribed_at']
        read_only_fields = ['id', 'subscribed_at']


class NewsletterSubscribeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Newsletter
        fields = ['email', 'name']

    def validate_email(self, value):
        if Newsletter.objects.filter(email__iexact=value, is_active=True).exists():
            raise serializers.ValidationError("This email is already subscribed.")
        return value.lower()

    def create(self, validated_data):
        validated_data['source'] = self.context.get('source', 'website')
        return super().create(validated_data)


class NewsletterCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterCampaign
        fields = [
            'id', 'subject', 'preheader', 'content', 'content_html',
            'status', 'scheduled_at', 'sent_at',
            'recipient_count', 'open_count', 'click_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'recipient_count', 'open_count', 'click_count',
                           'sent_at', 'created_at', 'updated_at']


class NewsletterCampaignListSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterCampaign
        fields = [
            'id', 'subject', 'preheader', 'status', 'scheduled_at', 'sent_at',
            'recipient_count', 'open_count', 'click_count', 'created_at'
        ]


from django.utils.text import slugify