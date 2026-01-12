from django.core.management.base import BaseCommand
from core.models import User, Agent
from core.utils import generate_employee_id

class Command(BaseCommand):
    help = 'Assigns employee_id to all Users and Agents that do not have one.'

    def handle(self, *args, **options):
        # 1. Users
        users = User.objects.filter(employee_id__isnull=True)
        count_users = 0
        for user in users:
            if not user.employee_id: # Double check
                new_id = generate_employee_id()
                user.employee_id = new_id
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Assigned User {user.username}: {new_id}"))
                count_users += 1

        # 2. Agents
        agents = Agent.objects.filter(employee_id__isnull=True)
        count_agents = 0
        for agent in agents:
            if not agent.employee_id:
                new_id = generate_employee_id()
                agent.employee_id = new_id
                agent.save()
                self.stdout.write(self.style.SUCCESS(f"Assigned Agent {agent.name}: {new_id}"))
                count_agents += 1

        self.stdout.write(self.style.SUCCESS(f"Completed. Users: {count_users}, Agents: {count_agents}"))
