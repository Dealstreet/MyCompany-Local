
import os
import django
from django.conf import settings
from django.template.loader import render_to_string
from django.template import Context, Template

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Account, Organization

try:
    # 1. Render using the file
    print("--- Rendering from file ---")
    # Mock context
    context = {
        'accounts': [
            {'financial_institution': 'TestBank', 'account_number': '12345', 'account_holder': 'Holder', 'nickname': 'Nick', 'id': 1, 'is_default': False}
        ],
        'user': {'organization': {'name': 'Org'}}
    }
    rendered = render_to_string('account_management_v2.html', context)
    
    if "TestBank" in rendered and "12345" in rendered:
        print("SUCCESS: Values rendered correctly.")
    else:
        print("FAILURE: Values NOT found.")
        # Print snippet where it should be
        idx = rendered.find('TestBank')
        if idx == -1:
             # Find where the loop is
             print("Snippet around loop:")
             # simplistic search
             start = rendered.find('account-scroll-container')
             print(rendered[start:start+500] if start != -1 else "Container not found")

    if "{{ account.financial_institution }}" in rendered:
        print("FAILURE: Found literal template tags in output!")

except Exception as e:
    print(f"Error: {e}")
