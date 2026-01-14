
import os
import django
import sys

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Stock
from core.views import identify_stock_country, get_naver_stock_name, get_naver_stock_extra_info
import yfinance as yf
import requests

def test_add_stock(keyword):
    print(f"Testing add stock for keyword: {keyword}")
    
    # 1. DB Search
    stock = Stock.objects.filter(name__icontains=keyword).first()
    if not stock:
        stock = Stock.objects.filter(code=keyword).first()
        
    if stock:
        print(f"Stock already exists: {stock.name} ({stock.code})")
        return

    print("Stock not found in DB. Trying External Search...")
    search_code = keyword
    
    # A. Search API
    if not (keyword.isdigit() and len(keyword) == 6):
        try:
            print("Searching Yahoo Finance API...")
            url = "https://query2.finance.yahoo.com/v1/finance/search"
            headers = {'User-Agent': 'Mozilla/5.0'}
            params = {'q': keyword, 'quotesCount': 5, 'newsCount': 0}
            
            response = requests.get(url, headers=headers, params=params, timeout=5)
            data = response.json()
            print(f"Search result: {data}")
            
            if 'quotes' in data and len(data['quotes']) > 0:
                found_ticker = None
                for q in data['quotes']:
                    symbol = q.get('symbol', '')
                    if symbol.endswith('.KS') or symbol.endswith('.KQ'):
                        found_ticker = symbol
                        break
                
                if not found_ticker:
                    found_ticker = data['quotes'][0]['symbol']
                    
                search_code = found_ticker
                print(f"Resolved code: {search_code}")
        except Exception as e:
            print(f"Search API failed: {e}")
            pass

    # B. yfinance
    if search_code.isdigit() and len(search_code) == 6:
            search_code = f"{search_code}.KS"
    
    print(f"Fetching yfinance for: {search_code}")
    ticker = yf.Ticker(search_code)
    
    try:
        info = ticker.fast_info
        current_price = info.last_price
        print(f"Current Price: {current_price}")
        
        if current_price:
            full_info = ticker.info
            print(f"Full Info fetched. Keys: {list(full_info.keys())[:5]}...")
            
            stock_name = keyword
            try: 
                stock_name = full_info.get('longName', full_info.get('shortName', keyword))
            except: 
                pass
            
            db_code = search_code
            if search_code.endswith('.KS'):
                check_code = search_code.replace('.KS', '')
                if check_code.isdigit() and len(check_code) == 6:
                    db_code = check_code
            
            print(f"DB Code: {db_code}")

            # Naver checks
            market_cap = None
            description = ""
            if db_code.isdigit() and len(db_code) == 6:
                naver_name = get_naver_stock_name(db_code)
                print(f"Naver Name: {naver_name}")
                if naver_name:
                    stock_name = naver_name
                
                naver_data = get_naver_stock_extra_info(db_code, full_info.get('exchange', ''))
                print(f"Naver Data: {naver_data}")
            
            country_ko = identify_stock_country(search_code, full_info)
            print(f"Country: {country_ko}")
            
            print("Attempting DB Creation...")
            stock, created = Stock.objects.get_or_create(
                code=db_code,
                defaults={
                    'name': stock_name,
                    'current_price': current_price,
                    'country': country_ko,
                }
            )
            print(f"Result: {stock} (Created: {created})")

    except Exception as e:
        print(f"yfinance/Processing Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Test with a known stock not in DB (delete if exists)
    target = "005930" # Samsung
    # Verify cleaning first
    st = Stock.objects.filter(code=target).first()
    if st:
        print(f"Deleting existing samsung stock for test...")
        st.delete()
        
    test_add_stock(target)
