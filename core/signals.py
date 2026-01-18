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


@receiver(post_save, sender=User)
def create_organization_for_new_user(sender, instance, created, **kwargs):
    """
    User 생성 시 자동으로 Organization을 생성하고 연결합니다.
    (SaaS 모델: 1인 1사 원칙)
    """
    if created and not instance.organization:
        # 1. Organization 생성
        org_name = f"{instance.username}의 회사"
        # 닉네임이 있다면 닉네임 우선 사용
        if instance.nickname:
             org_name = f"{instance.nickname}의 회사"
             
        org = Organization.objects.create(name=org_name, description="자동 생성된 회사입니다.")
        
        # 2. User 업데이트 (연결 및 CEO 권한 부여)
        instance.organization = org
        instance.role = 'ceo'
        instance.save()

