from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone

from client.models import Client

from .models import Transaction, Wallet


@receiver(post_save, sender=Transaction)
def update_wallet_on_transaction(sender, instance, created, **kwargs):
    """Update wallet balance when transaction is completed."""
    if created or instance.status == Transaction.Status.COMPLETED:
        if instance.direction == Transaction.Direction.INCOMING and instance.user:
            wallet, _ = Wallet.objects.get_or_create(user=instance.user)
            if instance.status == Transaction.Status.COMPLETED:
                wallet.add_funds(
                    instance.net_amount,
                    description=f'{instance.get_transaction_type_display()}',
                    reference_id=str(instance.id),
                    reference_type='transaction'
                )
        
        if instance.direction == Transaction.Direction.OUTGOING and instance.teacher:
            wallet, _ = Wallet.objects.get_or_create(user=instance.teacher)
            if instance.status == Transaction.Status.COMPLETED and instance.transaction_type == Transaction.Type.TEACHER_PAYOUT:
                wallet.deduct_funds(
                    instance.amount,
                    description=f'Payout',
                    reference_id=str(instance.id),
                    reference_type='payout'
                )


@receiver(post_save, sender=Client)
def create_wallet_for_user(sender, instance, created, **kwargs):
    if created:
        Wallet.objects.get_or_create(user=instance)