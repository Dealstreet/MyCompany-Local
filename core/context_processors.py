from .models import Agent, UserFavorite

def sidebar_data(request):
    context = {'agents': [], 'favorites': []}
    if request.user.is_authenticated and request.user.organization:
        context['agents'] = Agent.objects.filter(organization=request.user.organization)
        context['favorites'] = UserFavorite.objects.filter(user=request.user).order_by('display_order')
    return context