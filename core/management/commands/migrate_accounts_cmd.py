from django.core.management.base import BaseCommand
from core.models import Organization, Account, Transaction

class Command(BaseCommand):
    help = 'Migrate accounts data'

    def handle(self, *args, **kwargs):
        orgs = Organization.objects.all()
        for org in orgs:
            self.stdout.write(f"Processing Organization: {org.name}")
            
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
                self.stdout.write(f"  Created default account: {default_account}")
                
            # Migrate Transactions
            txs = Transaction.objects.filter(organization=org, account__isnull=True)
            count = txs.count()
            if count > 0:
                txs.update(account=default_account)
                self.stdout.write(f"  Linked {count} transactions to default account.")
            else:
                self.stdout.write("  No orphan transactions found.")
