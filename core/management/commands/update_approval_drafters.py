from django.core.management.base import BaseCommand
from core.models import Approval, Agent
from core.utils import get_agent_by_stock

class Command(BaseCommand):
    help = 'Update Approval drafters based on the stock mentioned in the document.'

    def handle(self, *args, **options):
        approvals = Approval.objects.all()
        updated_count = 0
        total_count = approvals.count()
        
        self.stdout.write(f"Scanning {total_count} approvals...")

        for approval in approvals:
            # Check if temp_stock_name or temp_stock_code exists
            stock_name = approval.temp_stock_name
            stock_code = approval.temp_stock_code
            
            if not stock_name and not stock_code:
                continue
                
            # Find correct agent
            correct_agent = get_agent_by_stock(stock_name, stock_code)
            
            if correct_agent:
                # If current agent is different (or None), update it
                if approval.agent != correct_agent:
                    self.stdout.write(f"Updating Approval #{approval.id}: {approval.title}")
                    self.stdout.write(f" - Old Agent: {approval.agent}")
                    self.stdout.write(f" - New Agent: {correct_agent}")
                    
                    approval.agent = correct_agent
                    approval.save()
                    updated_count += 1
            else:
                # self.stdout.write(f"No managing agent found for {stock_name} ({stock_code}) in Approval #{approval.id}")
                pass

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} approvals."))
