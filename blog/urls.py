from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryListView, TagListView, PostViewSet,
    CommentViewSet, NewsletterSubscribeView, NewsletterUnsubscribeView,
    NewsletterCampaignViewSet
)

router = DefaultRouter()
router.register(r'posts', PostViewSet, basename='post')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'campaigns', NewsletterCampaignViewSet, basename='campaign')

urlpatterns = [
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('tags/', TagListView.as_view(), name='tag-list'),

    path('newsletter/subscribe/', NewsletterSubscribeView.as_view(), name='newsletter-subscribe'),
    path('newsletter/unsubscribe/', NewsletterUnsubscribeView.as_view(), name='newsletter-unsubscribe'),
]