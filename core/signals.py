from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from .models import User, UserProfile, Transaction, Organization

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=Transaction)
@receiver(post_delete, sender=Transaction)
def recalculate_cash_balance(sender, instance, **kwargs):
    """
    Recalculates Organization's cash_balance whenever a Transaction is saved or deleted.
    This ensures data consistency even after manual DB edits or deletions.
    """
    org = instance.organization
    
    # Calculate Sum from all existing transactions
    total_cash = Transaction.objects.filter(organization=org).aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Update Organization
    # Avoid recursion by using update() or ensuring save doesn't trigger loop (org save safe here)
    Organization.objects.filter(id=org.id).update(cash_balance=total_cash)

