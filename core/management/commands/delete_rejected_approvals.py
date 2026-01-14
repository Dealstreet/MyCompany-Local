from django.core.management.base import BaseCommand
from core.models import Approval

class Command(BaseCommand):
    help = 'Deletes all Approval documents with rejected status'

    def handle(self, *args, **options):
        rejected_approvals = Approval.objects.filter(status='rejected')
        count = rejected_approvals.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No rejected approvals found to delete.'))
            return

        self.stdout.write(f'Found {count} rejected approvals. Deleting...')
        
        # Deleting
        rejected_approvals.delete()
        
        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {count} rejected approvals.'))
