# core/context_processors.py
from .models import Agent

def sidebar_agents(request):
    if request.user.is_authenticated and request.user.organization:
        return {
            'agents': Agent.objects.filter(organization=request.user.organization)
        }
    return {'agents': []}