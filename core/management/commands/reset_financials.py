from django.core.management.base import BaseCommand
from core.models import Transaction, DailySnapshot, Organization, InvestmentLog

class Command(BaseCommand):
    help = 'Resets all financial data (Transactions, Snapshots, Cash Balance)'

    def handle(self, *args, **options):
        self.stdout.write("Resetting financial data...")

        # 1. Delete Transactions
        count_tx, _ = Transaction.objects.all().delete()
        self.stdout.write(f"Deleted {count_tx} transactions.")

        # 2. Delete Snapshots
        count_snap, _ = DailySnapshot.objects.all().delete()
        self.stdout.write(f"Deleted {count_snap} daily snapshots.")
        
        # 3. Reset Organization Cash Balance
        for org in Organization.objects.all():
            org.cash_balance = 0
            org.save()
            self.stdout.write(f"Reset cash balance for {org.name} to 0.")

        self.stdout.write(self.style.SUCCESS("Successfully reset all financial data."))
