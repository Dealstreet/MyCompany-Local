import FinanceDataReader as fdr
from datetime import datetime
from django.utils import timezone
from .models import Stock

def update_stock(stock):
    try:
        # 0. Sanitize code (Remove KRX: prefix if exists)
        code = stock.code.replace('KRX:', '')
        
        # 1. Fetch data
        df = fdr.DataReader(code) 
        
        if df.empty:
            print(f"No data found for {stock.name} ({stock.code})")
            return False

        # 2. Update basic info (Last row)
        last_row = df.iloc[-1]
        stock.current_price = float(last_row['Close'])
        
        # 3. Calculate 52-week High/Low
        one_year_df = df.tail(252)
        stock.high_52w = float(one_year_df['High'].max())
        stock.low_52w = float(one_year_df['Low'].min())

        # 4. Candle Data (Full history)
        candle_data = []
        for index, row in df.iterrows():
            candle_data.append({
                "date": index.strftime('%Y-%m-%d'),
                "close": float(row['Close'])
            })
        stock.candle_data = candle_data
        
        stock.save()
        print(f"Updated {stock.name} ({stock.code})")
        return True
        
    except Exception as e:
        print(f"Failed to update {stock.name} ({stock.code}): {e}")
        return False

def update_all_stocks():
    print("Updating stock data...")
    stocks = Stock.objects.all()
    count = 0
    for stock in stocks:
        if update_stock(stock):
            count += 1
    print(f"Finished updating {count} stocks.")
