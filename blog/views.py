from rest_framework.decorators import action
from django.db.models import Count, Exists, OuterRef, Q, F
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import Category, Tag, Post, Comment, PostLike, PostView, CommentLike, Newsletter, NewsletterCampaign
from .serializers import (
    CategorySerializer, TagSerializer,
    PostListSerializer, PostDetailSerializer, PostCreateUpdateSerializer,
    CommentSerializer, CommentCreateSerializer, NewsletterSubscribeSerializer,
    NewsletterCampaignSerializer, NewsletterCampaignListSerializer
)
from client.permissions import IsAccountOwnerOrStaff


class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True).annotate(
        posts_count=Count('posts', filter=Q(posts__status=Post.Status.PUBLISHED, posts__visibility=Post.Visibility.PUBLIC))
    )
    pagination_class = None


class TagListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TagSerializer
    queryset = Tag.objects.annotate(
        posts_count=Count('posts', filter=Q(posts__status=Post.Status.PUBLISHED, posts__visibility=Post.Visibility.PUBLIC))
    ).filter(posts_count__gt=0)
    pagination_class = None


class PostViewSet(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'excerpt', 'content', 'author__display_name', 'tags__name']
    ordering_fields = ['published_at', 'created_at', 'view_count', 'like_count', 'comment_count', 'reading_time']
    ordering = ['-published_at']

    def get_queryset(self):
        user = self.request.user
        base = Post.objects.select_related('author', 'category').prefetch_related('tags')

        if self.action == 'list':
            if user.is_authenticated and (user.is_staff or user.role == user.Role.MODERATOR):
                return base
            return base.filter(status=Post.Status.PUBLISHED, visibility=Post.Visibility.PUBLIC)

        if self.action in ['retrieve', 'like', 'bookmark', 'comments']:
            if user.is_authenticated and (user.is_staff or user.role == user.Role.MODERATOR):
                return base
            return base.filter(
                Q(status=Post.Status.PUBLISHED, visibility=Post.Visibility.PUBLIC) |
                Q(author=user)
            ).distinct()

        return base.filter(author=user)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PostCreateUpdateSerializer
        if self.action == 'retrieve':
            return PostDetailSerializer
        return PostListSerializer

    def get_permissions(self):
        if self.action in ['create']:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'destroy', 'publish', 'unpublish', 'feature']:
            return [IsAuthenticated(), IsAccountOwnerOrStaff()]
        return [AllowAny()]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Filters
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__slug=category)

        tag = request.query_params.get('tag')
        if tag:
            queryset = queryset.filter(tags__slug=tag)

        author = request.query_params.get('author')
        if author:
            queryset = queryset.filter(author__id=author)

        featured = request.query_params.get('featured')
        if featured == 'true':
            queryset = queryset.filter(is_featured=True)

        # Annotate user-specific fields
        if request.user.is_authenticated:
            liked_subquery = PostLike.objects.filter(post=OuterRef('pk'), user=request.user)
            bookmarked_subquery = Post.bookmarks.through.objects.filter(post=OuterRef('pk'), user=request.user)
            queryset = queryset.annotate(
                liked_by_current_user=Exists(liked_subquery),
                bookmarked_by_current_user=Exists(bookmarked_subquery)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # Track view
        self._track_view(instance, request)

        # Annotate user-specific fields
        if request.user.is_authenticated:
            instance.liked_by_current_user = PostLike.objects.filter(post=instance, user=request.user).exists()
            instance.bookmarked_by_current_user = instance.bookmarks.filter(user=request.user).exists()

        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    def _track_view(self, post, request):
        if request.user.is_authenticated:
            user = request.user
            session_key = None
        else:
            user = None
            session_key = request.session.session_key
            if not session_key:
                request.session.create()
                session_key = request.session.session_key

        PostView.objects.get_or_create(
            post=post,
            user=user,
            session_key=session_key or '',
            defaults={
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'referrer': request.META.get('HTTP_REFERER', ''),
            }
        )
        Post.objects.filter(pk=post.pk).update(view_count=F('view_count') + 1)

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def like(self, request, *args, **kwargs):
        post = self.get_object()
        like, created = PostLike.objects.get_or_create(post=post, user=request.user)

        if not created:
            like.delete()
            Post.objects.filter(pk=post.pk).update(like_count=F('like_count') - 1)
            return Response({'liked': False, 'like_count': post.like_count - 1})

        Post.objects.filter(pk=post.pk).update(like_count=F('like_count') + 1)
        return Response({'liked': True, 'like_count': post.like_count + 1}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def bookmark(self, request, *args, **kwargs):
        post = self.get_object()
        bookmark, created = post.bookmarks.get_or_create(user=request.user)

        if not created:
            bookmark.delete()
            return Response({'bookmarked': False})

        return Response({'bookmarked': True}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], permission_classes=[AllowAny])
    def comments(self, request, *args, **kwargs):
        post = self.get_object()

        if request.method == 'GET':
            comments = post.comments.filter(parent__isnull=True, is_approved=True).select_related('author').prefetch_related('replies__author')
            serializer = CommentSerializer(comments, many=True, context={'request': request})
            return Response(serializer.data)

        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = CommentCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(post=post)
        Post.objects.filter(pk=post.pk).update(comment_count=F('comment_count') + 1)
        return Response(CommentSerializer(serializer.instance, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAccountOwnerOrStaff])
    def publish(self, request, *args, **kwargs):
        post = self.get_object()
        if post.status == Post.Status.PUBLISHED:
            return Response({'detail': 'Already published.'}, status=status.HTTP_400_BAD_REQUEST)
        post.status = Post.Status.PUBLISHED
        post.published_at = timezone.now()
        post.save(update_fields=['status', 'published_at'])
        return Response(PostDetailSerializer(post, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAccountOwnerOrStaff])
    def unpublish(self, request, *args, **kwargs):
        post = self.get_object()
        post.status = Post.Status.DRAFT
        post.save(update_fields=['status'])
        return Response(PostDetailSerializer(post, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def feature(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'error': 'Staff only.'}, status=status.HTTP_403_FORBIDDEN)
        post = self.get_object()
        post.is_featured = not post.is_featured
        post.save(update_fields=['is_featured'])
        return Response({'is_featured': post.is_featured})

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_posts(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)


class CommentViewSet(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = CommentSerializer

    def get_queryset(self):
        return Comment.objects.select_related('author', 'post').filter(is_approved=True)

    def get_object(self):
        return get_object_or_404(Comment, pk=self.kwargs['pk'])

    def retrieve(self, request, *args, **kwargs):
        comment = self.get_object()
        serializer = self.get_serializer(comment, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def like(self, request, *args, **kwargs):
        comment = self.get_object()
        like, created = CommentLike.objects.get_or_create(comment=comment, user=request.user)

        if not created:
            like.delete()
            Comment.objects.filter(pk=comment.pk).update(like_count=F('like_count') - 1)
            return Response({'liked': False, 'like_count': comment.like_count - 1})

        Comment.objects.filter(pk=comment.pk).update(like_count=F('like_count') + 1)
        return Response({'liked': True, 'like_count': comment.like_count + 1}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAccountOwnerOrStaff])
    def approve(self, request, *args, **kwargs):
        comment = self.get_object()
        if not (request.user.is_staff or comment.post.author == request.user):
            return Response({'error': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        comment.is_approved = True
        comment.save(update_fields=['is_approved'])
        return Response(CommentSerializer(comment, context={'request': request}).data)


class NewsletterSubscribeView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsletterSubscribeSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'source': 'api', 'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'message': 'Successfully subscribed to newsletter.'}, status=status.HTTP_201_CREATED)


class NewsletterUnsubscribeView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            subscription = Newsletter.objects.get(email__iexact=email, is_active=True)
            subscription.is_active = False
            subscription.unsubscribed_at = timezone.now()
            subscription.save(update_fields=['is_active', 'unsubscribed_at'])
        except Newsletter.DoesNotExist:
            pass

        return Response({'message': 'Unsubscribed successfully.'})


class NewsletterCampaignViewSet(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NewsletterCampaignSerializer
    queryset = NewsletterCampaign.objects.all()
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return NewsletterCampaignListSerializer
        return NewsletterCampaignSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'error': 'Staff only.'}, status=status.HTTP_403_FORBIDDEN)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'error': 'Staff only.'}, status=status.HTTP_403_FORBIDDEN)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'error': 'Staff only.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def send(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'error': 'Staff only.'}, status=status.HTTP_403_FORBIDDEN)
        campaign = self.get_object()
        # TODO: Implement actual sending logic
        campaign.status = NewsletterCampaign.Status.SENT
        campaign.sent_at = timezone.now()
        campaign.recipient_count = Newsletter.objects.filter(is_active=True).count()
        campaign.save()
        return Response({'detail': 'Campaign sent.', 'recipient_count': campaign.recipient_count})