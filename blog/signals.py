from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.db.models import Count, F
from .models import Post, Comment, PostLike, CommentLike, PostView, Tag


@receiver(post_save, sender=PostLike)
def update_post_like_count(sender, instance, created, **kwargs):
    if created:
        Post.objects.filter(pk=instance.post_id).update(like_count=F('like_count') + 1)
    else:
        Post.objects.filter(pk=instance.post_id).update(like_count=F('like_count') - 1)


@receiver(post_delete, sender=PostLike)
def update_post_like_count_on_delete(sender, instance, **kwargs):
    Post.objects.filter(pk=instance.post_id).update(like_count=F('like_count') - 1)


@receiver(post_save, sender=CommentLike)
def update_comment_like_count(sender, instance, created, **kwargs):
    if created:
        Comment.objects.filter(pk=instance.comment_id).update(like_count=F('like_count') + 1)
    else:
        Comment.objects.filter(pk=instance.comment_id).update(like_count=F('like_count') - 1)


@receiver(post_delete, sender=CommentLike)
def update_comment_like_count_on_delete(sender, instance, **kwargs):
    Comment.objects.filter(pk=instance.comment_id).update(like_count=F('like_count') - 1)


@receiver(post_save, sender=Comment)
def update_post_comment_count(sender, instance, created, **kwargs):
    if created and instance.is_approved:
        Post.objects.filter(pk=instance.post_id).update(comment_count=F('comment_count') + 1)


@receiver(post_delete, sender=Comment)
def update_post_comment_count_on_delete(sender, instance, **kwargs):
    if instance.is_approved:
        Post.objects.filter(pk=instance.post_id).update(comment_count=F('comment_count') - 1)


@receiver(post_save, sender=PostView)
def update_post_view_count(sender, instance, created, **kwargs):
    if created:
        Post.objects.filter(pk=instance.post_id).update(view_count=F('view_count') + 1)


@receiver(m2m_changed, sender=Post.tags.through)
def update_tag_posts_count(sender, instance, action, **kwargs):
    if action in ['post_add', 'post_remove', 'post_clear']:
        tags = instance.tags.all() if action != 'post_clear' else Tag.objects.filter(posts=instance)
        for tag in tags:
            tag.posts_count = tag.posts.filter(
                status=Post.Status.PUBLISHED,
                visibility=Post.Visibility.PUBLIC
            ).count()
            tag.save(update_fields=['posts_count'])