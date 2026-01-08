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

import re

def parse_mirae_sms(sms_text):
    """
    미래에셋증권 문자 파싱 함수
    반환: {'stock_name':..., 'price':..., ...} 또는 None
    """
    data = {}
    patterns = {
        'stock_info': r'종목명\s*:\s*(.*?)\(([A-Z0-9]+)\)', 
        'trade_type': r'매매구분\s*:\s*(매수|매도)',
        'qty': r'체결수량\s*:\s*([\d,]+)주',
        'price': r'체결단가\s*:\s*([\d,]+)원',
        'order_no': r'주문번호\s*:\s*(\d+)',
    }

    try:
        # 종목명 파싱
        stock_match = re.search(patterns['stock_info'], sms_text)
        if stock_match:
            data['stock_name'] = stock_match.group(1).strip()
            data['stock_code'] = stock_match.group(2).strip()
        
        # 매매구분
        type_match = re.search(patterns['trade_type'], sms_text)
        data['trade_type'] = type_match.group(1) if type_match else '기타'

        # 수량 (쉼표 제거)
        qty_match = re.search(patterns['qty'], sms_text)
        data['quantity'] = int(qty_match.group(1).replace(',', '')) if qty_match else 0

        # 가격 (쉼표 제거)
        price_match = re.search(patterns['price'], sms_text)
        data['price'] = int(price_match.group(1).replace(',', '')) if price_match else 0
        
        # 주문번호
        order_match = re.search(patterns['order_no'], sms_text)
        data['order_no'] = order_match.group(1) if order_match else None
        
        # 필수값이 없으면 실패 처리
        if not data.get('order_no'):
            return None
            
        return data

    except Exception as e:
        print(f"Parsing Error: {e}")
        return None
