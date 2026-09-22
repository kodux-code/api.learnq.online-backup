from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import F
from django.conf import settings
from django.utils import timezone

from client.models import Client
from transaction.models import Wallet

from .models import Order, OrderItem, Subscription, Coupon

@receiver(post_save, sender=Order)
def update_order_items_on_complete(sender, instance, **kwargs):
    """Create earning transactions when order completes"""
    if instance.status == Order.Status.COMPLETED and not getattr(instance, '_earnings_created', False):
        from earning.models import TeacherEarning
        from transaction.models import Transaction
        from course.models import Enrollment

        for item in instance.items.filter(item_type=OrderItem.ItemType.COURSE, teacher__isnull=False):
            teacher = item.teacher
            earning, _ = TeacherEarning.objects.get_or_create(teacher=teacher)
            earning.add_earning(item.teacher_amount)

            Transaction.objects.create(
                user=instance.user,
                direction=Transaction.Direction.INCOMING,
                transaction_type=Transaction.Type.COURSE_SALE,
                status=Transaction.Status.COMPLETED,
                amount=item.total_price,
                net_amount=item.teacher_amount,
                platform_fee=item.total_price - item.teacher_amount,
                currency=instance.currency,
                course=item.course,
                order=instance,
                teacher=teacher,
                teacher_amount=item.teacher_amount,
                description=f"Sale of {item.name} to {instance.user.display_name}",
                completed_at=timezone.now()
            ).mark_completed()

        # Mark to avoid duplicate processing
        instance._earnings_created = True


@receiver(post_save, sender=Subscription)
def update_subscription_on_cancel(sender, instance, **kwargs):
    if instance.status == Subscription.Status.CANCELLED and instance.ended_at:
        # Revoke access to subscription content
        pass  # Implement content access revocation


@receiver(post_save, sender=Order)
def update_coupon_usage(sender, instance, created, **kwargs):
    if instance.coupon and created:
        Coupon.objects.filter(pk=instance.coupon_id).update(used_count=F('used_count') + 1)


@receiver(post_save, sender=Wallet)
def create_wallet_for_user(sender, instance, created, **kwargs):
    if created:
        Wallet.objects.get_or_create(user=instance)


from django.db.models.signals import post_save as ps
ps.connect(create_wallet_for_user, sender=Client)