import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import F

from .models import Question, Answer, Vote

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Vote)
def update_vote_score(sender, instance, created, **kwargs):
    """Update vote score on target when vote is created/updated."""
    if instance.question:
        Question.objects.filter(pk=instance.question_id).update(
            updated_at=timezone.now()
        )
    elif instance.answer:
        Answer.objects.filter(pk=instance.answer_id).update(
            updated_at=timezone.now()
        )


@receiver(post_delete, sender=Vote)
def update_vote_score_on_delete(sender, instance, **kwargs):
    """Update vote score on target when vote is deleted."""
    if instance.question:
        Question.objects.filter(pk=instance.question_id).update(
            updated_at=timezone.now()
        )
    elif instance.answer:
        Answer.objects.filter(pk=instance.answer_id).update(
            updated_at=timezone.now()
        )


@receiver(post_save, sender=Answer)
def update_answer_count_on_create(sender, instance, created, **kwargs):
    if created:
        Question.objects.filter(pk=instance.question_id).update(
            answer_count=F('answer_count') + 1,
            updated_at=timezone.now()
        )


@receiver(post_delete, sender=Answer)
def update_answer_count_on_delete(sender, instance, **kwargs):
    Question.objects.filter(pk=instance.question_id).update(
        answer_count=F('answer_count') - 1,
        updated_at=timezone.now()
    )


@receiver(post_save, sender=Question)
def update_tag_question_count(sender, instance, **kwargs):
    if instance.tags:
        for tag in instance.tags.all():
            tag.question_count = tag.questions.filter(is_deleted=False).count()
            tag.save(update_fields=['question_count'])


@receiver(post_save, sender=Question)
def update_share_count(sender, instance, **kwargs):
    pass  # share_count is computed dynamically


from django.utils import timezone
from django.db.models.signals import m2m_changed


@receiver(m2m_changed, sender=Question.tags.through)
def update_tag_question_count_on_change(sender, instance, action, **kwargs):
    if action in ['post_add', 'post_remove', 'post_clear']:
        tags = instance.tags.all() if action != 'post_clear' else QuestionTag.objects.filter(questions=instance)
        for tag in tags:
            tag.question_count = tag.questions.filter(is_deleted=False).count()
            tag.save(update_fields=['question_count'])