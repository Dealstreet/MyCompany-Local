import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Agent, Department

agents = Agent.objects.all()
for agent in agents:
    dept_name = agent.department
    try:
        dept_obj = Department.objects.get(name=dept_name, organization=agent.organization)
        agent.department_obj = dept_obj
        agent.save()
        print(f"Linked Agent {agent.name} to Department {dept_obj.name}")
    except Department.DoesNotExist:
        print(f"Warning: Department '{dept_name}' not found for Agent {agent.name}. Trying to create or ignore.")
        # Optional: Create it if it doesn't exist? User seemingly asked to match existing.
    except Department.MultipleObjectsReturned:
        print(f"Warning: Multiple departments found for {dept_name}")
        
    except Exception as e:
        print(f"Error processing {agent.name}: {e}")
