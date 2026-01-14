import os
import django
import sys

# Setup Django environment
sys.path.append(r'c:\Users\jaeho\Desktop\MyCompany-Local')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mycompany.settings')
django.setup()

from core.models import Stock

try:
    stock = Stock.objects.get(code__icontains='TQQQ') # or name
    print(f"Stock: {stock.name} ({stock.code})")
    print(f"Country: '{stock.country}'")
except Stock.DoesNotExist:
    # Try searching by name if code fails
    try:
        stock = Stock.objects.get(name__icontains='TQQQ')
        print(f"Stock: {stock.name} ({stock.code})")
        print(f"Country: '{stock.country}'")
    except Stock.DoesNotExist:
        print("TQQQ not found.")
        # List all stocks to see what's there
        print("Available US-like stocks:")
        for s in Stock.objects.all():
            print(f"- {s.name}: '{s.country}'")

