from django.core.management.base import BaseCommand
from core.models import Organization, Account, Transaction
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def migrate_accounts():
    orgs = Organization.objects.all()
    for org in orgs:
        print(f"Processing Organization: {org.name}")
        
        # Check/Create Default Account
        default_account = Account.objects.filter(organization=org, is_default=True).first()
        if not default_account:
            default_account = Account.objects.create(
                organization=org,
                financial_institution="미래에셋증권",
                account_number="기본계좌",
                account_holder=org.name,
                nickname="기본 주식계좌",
                is_default=True
            )
            print(f"  Created default account: {default_account}")
            
        # Migrate Transactions
        txs = Transaction.objects.filter(organization=org, account__isnull=True)
        count = txs.count()
        if count > 0:
            txs.update(account=default_account)
            print(f"  Linked {count} transactions to default account.")
        else:
            print("  No orphan transactions found.")

if __name__ == '__main__':
    migrate_accounts()
