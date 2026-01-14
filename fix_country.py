import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.models import Stock

try:
    s = Stock.objects.get(name='SK하이닉스')
    print(f"Code: {s.code}")
    print(f"Current Country: '{s.country}'")
    
    if s.country != '한국':
        print("Fixing country to '한국'")
        s.country = '한국'
        s.save()
        print("Fixed.")
    else:
        print("Country is already correct.")

except Exception as e:
    print(f"Error: {e}")
