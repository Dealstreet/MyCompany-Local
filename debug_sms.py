import re

def parse_mirae_sms(sms_text):
    data = {}
    patterns = {
        'stock_info': r'종목명\s*:\s*(.*?)\(([A-Z0-9]+)\)', 
        'trade_type': r'매매구분\s*:\s*(매수|매도)',
        'qty': r'체결수량\s*:\s*([\d,]+)주',
        'price': r'체결단가\s*:\s*([\d,]+)원',
        'order_no': r'주문번호\s*:\s*(\d+)',
    }

    try:
        print(f"Analyzing text:\n{sms_text}\n")

        # 종목명 파싱
        stock_match = re.search(patterns['stock_info'], sms_text)
        if stock_match:
            data['stock_name'] = stock_match.group(1).strip()
            data['stock_code'] = stock_match.group(2).strip()
            print(f"Found Stock: {data['stock_name']} ({data['stock_code']})")
        else:
            print("Failed to match Stock Info")
        
        # 매매구분
        type_match = re.search(patterns['trade_type'], sms_text)
        data['trade_type'] = type_match.group(1) if type_match else '기타'

        # 수량
        qty_match = re.search(patterns['qty'], sms_text)
        data['quantity'] = int(qty_match.group(1).replace(',', '')) if qty_match else 0

        # 가격
        price_match = re.search(patterns['price'], sms_text)
        data['price'] = int(price_match.group(1).replace(',', '')) if price_match else 0
        
        # 주문번호
        order_match = re.search(patterns['order_no'], sms_text)
        data['order_no'] = order_match.group(1) if order_match else None
        print(f"Found Order No: {data['order_no']}")
        
        if not data.get('order_no'):
            return None
            
        return data

    except Exception as e:
        print(f"Parsing Error: {e}")
        return None

user_text = """[미래에셋증권 알림]
[Web발신]
[미래에셋증권] 전량체결
계좌번호 : 202-54**-**38-0
계좌명 : 이재호
종목명 : TIGER 미국나스닥100(133690)
매매구분 : 매수
주문수량 : 1주
체결수량 : 1주
체결단가 : 1,000원
체결금액 : 1,000원
주문번호 : 123456"""

result = parse_mirae_sms(user_text)
print("\nResult:", result)
