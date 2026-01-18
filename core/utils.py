import re
from django.utils import timezone
from django.db.models import Max, Q
from django.apps import apps

def generate_employee_id():
    """
    Generates a unique employee_id in the format YYYYNNN (e.g., 2026001).
    It checks both User and Agent models to ensure uniqueness across the system.
    """
    User = apps.get_model('core', 'User')
    Agent = apps.get_model('core', 'Agent')

    year = timezone.now().year
    prefix = str(year)

    # Find max ID for the current year in both tables
    max_user_id = User.objects.filter(employee_id__startswith=prefix).aggregate(Max('employee_id'))['employee_id__max']
    max_agent_id = Agent.objects.filter(employee_id__startswith=prefix).aggregate(Max('employee_id'))['employee_id__max']

    current_max = 0
    
    if max_user_id:
        try:
            current_max = max(current_max, int(max_user_id))
        except ValueError:
            pass
            
    if max_agent_id:
        try:
            current_max = max(current_max, int(max_agent_id))
        except ValueError:
            pass

    if current_max == 0:
        # Start of the year
        return f"{prefix}001"
    else:
        # Increment
        return str(current_max + 1)

def parse_mirae_sms(text):
    """
    미래에셋증권 SMS 파싱 함수 (복원됨)
    예상 포맷: [미래에셋] 매수체결 삼성전자 10주 70,000원
    """
    if not text:
        return None

    result = {
        'stock_name': None,
        'stock_code': None,
        'quantity': 0,
        'price': 0,
        'amount': 0,
        'trade_type': None # 'buy' or 'sell'
    }

    # 1. 거래 유형 식별
    if '매수' in text:
        result['trade_type'] = 'buy'
    elif '매도' in text:
        result['trade_type'] = 'sell'
    else:
        return None # 매매 관련 아니면 무시

    # 2. 종목명/코드 추출 (간이 로직)
    # 괄호 안의 숫자(6자리)는 코드로 인식 -> (005930)
    code_match = re.search(r'\(\d{6}\)', text)
    if code_match:
        result['stock_code'] = code_match.group(0).strip('()')
    
    # 종목명은 일반적으로 [미래에셋] 뒤, 혹은 체결 단어 뒤에 옴
    # 예: "매수체결 삼성전자"
    # 여기서는 단순화를 위해 정교한 NLP 대신 공백 기준 일부 추출 시도
    # 실제로는 LLM이나 더 복잡한 정규식이 필요할 수 있음
    
    # 3. 수량, 단가 추출
    # "10주", "1,000원" 패턴 찾기
    qty_match = re.search(r'(\d+[,\d]*)\s*주', text)
    if qty_match:
        result['quantity'] = int(qty_match.group(1).replace(',', ''))
        
    price_match = re.search(r'(\d+[,\d]*)\s*원', text)
    if price_match:
        result['price'] = int(price_match.group(1).replace(',', ''))

    if result['quantity'] and result['price']:
        result['amount'] = result['quantity'] * result['price']

    return result

def number_to_hangul(number):
    """
    Converts an integer to Korean number string (e.g. 1000 -> 일천).
    Simple implementation for amounts.
    """
    if number == 0:
        return "영"
    
    units = ["", "만", "억", "조"]
    nums = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
    
    result = []
    str_num = str(number)
    length = len(str_num)
    
    # 4자리씩 끊어서 처리
    # Reversing to process chunks of 4
    reversed_str = str_num[::-1]
    chunks = [reversed_str[i:i+4][::-1] for i in range(0, length, 4)]
    
    for i, chunk in enumerate(chunks):
        chunk_num = int(chunk)
        if chunk_num == 0:
            continue
            
        chunk_str = ""
        for j, digit in enumerate(chunk):
            n = int(digit)
            if n == 0:
                continue
                
            # 자릿수 (천, 백, 십, 일)
            pos = len(chunk) - 1 - j
            
            # 1일 경우: 십, 백, 천 단위에서는 생략 가능 (예: 일백 -> 백), 하지만 '금 일천 원' 형식은 '일'을 붙이는 경우가 많음
            # 금융권/공문서 정석은 '일금 일천 원'
            chunk_str += nums[n]
            
            if pos == 1:
                chunk_str += "십"
            elif pos == 2:
                chunk_str += "백"
            elif pos == 3:
                chunk_str += "천"
                
        result.append(chunk_str + units[i])
        
    return "".join(reversed(result))

def format_approval_content(stock_name, stock_code, quantity, price, total_amount, trade_type, date=None, reason="", include_attachment=True, order_no="N/A", account_info="미래에셋증권 (예금주: 꼼망컴퍼니)"):
    """
    Generates standardized approval document content.
    """
    if not date:
        date = timezone.now().date()
        
    # 날짜 분해
    year = date.year
    month = date.month
    day = date.day
    # 요일 구하기
    days = ['월', '화', '수', '목', '금', '토', '일']
    weekday = days[date.weekday()]
    
    # 한글 금액 변환
    amount_hangul = number_to_hangul(total_amount)
    
    # 매매구분 한글
    trade_type_kor = "매수" if trade_type == 'buy' else "매도"
    
    # [공통 서식] 주식 매매 체결 결과 보고서 (HTML 변환)
    # Summernote 에디터 호환을 위해 HTML 태그 사용

    template = f"""
    <h3 style="text-align: center; font-weight: bold;">주식 매매 체결 결과 보고서</h3>
    <br>
    <p><b>1. 관련:</b> {stock_name} {quantity:,}주 주당 {price:,}원 {trade_type_kor}</p>
    <p><b>2. 위와 관련하여 주식 {trade_type_kor} 체결 결과를 아래와 같이 보고합니다.</b></p>
    <div style="margin-left: 20px;">
        <p><b>가. 체결 개요</b></p>
        <ul style="list-style-type: none; padding-left: 20px;">
            <li>1) 일자: {year}년 {month}월 {day}일 ({weekday})</li>
            <li>2) 계좌: {account_info}</li>
            <li>3) 주문 번호: {order_no}</li>
        </ul>
        <br>
        <p><b>나. 체결 상세 내역</b></p>
        <table class="table table-bordered" style="width: 100%; border-collapse: collapse; text-align: center; border: 1px solid black;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th style="border: 1px solid black; padding: 8px;">종목명(종목코드)</th>
                    <th style="border: 1px solid black; padding: 8px;">매매 구분</th>
                    <th style="border: 1px solid black; padding: 8px;">체결 수량</th>
                    <th style="border: 1px solid black; padding: 8px;">체결 단가</th>
                    <th style="border: 1px solid black; padding: 8px;">체결 금액</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="border: 1px solid black; padding: 8px;">{stock_name}<br>({stock_code})</td>
                    <td style="border: 1px solid black; padding: 8px;">{trade_type_kor}</td>
                    <td style="border: 1px solid black; padding: 8px;">{quantity:,} 주</td>
                    <td style="border: 1px solid black; padding: 8px;">{price:,} 원</td>
                    <td style="border: 1px solid black; padding: 8px;">금 {total_amount:,} 원</td>
                </tr>
            </tbody>
        </table>
    </div>
    <br>
    <p><b>3. 비고:</b> {reason if reason else 'CEO 직접 지시' if not include_attachment else 'SMS 체결 알림'}</p>
    """
    if include_attachment:
        template += "<br><p>붙임 매매 체결 확인서(문자 알림 사본) 1부. 끝.</p>"
    else:
        template += "<br><p>끝.</p>"
        
    return template

def get_agent_by_stock(stock_name, stock_code):
    """
    Returns the Agent who manages the given stock (by name or code).
    Returns None if no matching stock or agent is found.
    """
    Stock = apps.get_model('core', 'Stock')
    Agent = apps.get_model('core', 'Agent')
    
    stock_obj = None
    
    # 1. Try to find stock by code
    if stock_code:
        stock_obj = Stock.objects.filter(code=stock_code).first()
        
    # 2. Try to find stock by name if not found by code
    if not stock_obj and stock_name:
        stock_obj = Stock.objects.filter(name=stock_name).first()
        
    if stock_obj:
        # Find agent managing this stock
        # [Refactor] Agent.stock removed -> use Stock.agent
        return stock_obj.agent
        
    return None


import yfinance as yf

def update_stock(stock_obj):
    """
    Updates a single Stock object with data from Yahoo Finance.
    Returns True if successful, False otherwise.
    """
    try:
        # 1. Resolve Symbol
        symbol = stock_obj.code
        
        # Check if Korean stock (6 digits) without suffix
        if symbol.isdigit() and len(symbol) == 6:
            # Try .KS first (KOSPI), then .KQ (KOSDAQ) - Naive approach
            # Or assume .KS for now, or check metadata. 
            # Better strategy: Try .KS, if error/empty, try .KQ
            try_symbols = [f"{symbol}.KS", f"{symbol}.KQ"]
        else:
            try_symbols = [symbol]

        ticker = None
        info = None
        
        for sym in try_symbols:
            t = yf.Ticker(sym)
            try:
                # fast_info is faster and often sufficient for price
                i = t.fast_info
                if i.last_price is not None:
                    ticker = t
                    info = i
                    break
            except Exception:
                continue
        
        if not ticker:
            print(f"Failed to find ticker for {stock_obj.name} ({stock_obj.code})")
            return False

        # 2. Update Basic Info
        stock_obj.current_price = info.last_price
        
        # Extended Info (Regular info dict for some fields)
        try:
            full_info = ticker.info
            stock_obj.high_52w = full_info.get('fiftyTwoWeekHigh')
            stock_obj.low_52w = full_info.get('fiftyTwoWeekLow')
            stock_obj.market_cap = full_info.get('marketCap')
            stock_obj.per = full_info.get('trailingPE')
            stock_obj.pbr = full_info.get('priceToBook')
            stock_obj.description = full_info.get('longBusinessSummary') or ""
            
            # Country Check (if empty)
            if not stock_obj.country:
                ctry = full_info.get('country', '')
                if ctry == 'South Korea': stock_obj.country = '한국'
                elif ctry == 'United States': stock_obj.country = '미국'
                else: stock_obj.country = ctry
            
            # [Naver Integration] 
            # Prioritize Naver for Korean stocks or general description
            # This logic was migrated from views.py
            if stock_obj.code.isdigit() and len(stock_obj.code) == 6:
                naver_data = get_naver_stock_extra_info(stock_obj.code)
                if naver_data.get('market_cap'):
                    stock_obj.market_cap = naver_data['market_cap']
                
                # Naver Description
                if naver_data.get('description'):
                    stock_obj.description = naver_data['description']
                
                # Naver Name Check
                naver_name = get_naver_stock_name(stock_obj.code)
                if naver_name and naver_name != stock_obj.name:
                    stock_obj.name = naver_name
                    
        except Exception as e:
            print(f"Error fetching full info for {stock_obj.name}: {e}")

        # 3. Update Candle Data (Optimize: Fetch 1mo and merge)
        try:
            # Fetch recent 1 month data
            hist = ticker.history(period="1mo", interval="1wk")
            
            new_data = []
            for date, row in hist.iterrows():
                # ApexCharts expects timestamp in ms
                ts = int(date.timestamp() * 1000)
                new_data.append({
                    'x': ts,
                    'y': [row['Open'], row['High'], row['Low'], row['Close']]
                })
            
            # Load existing data
            existing_data = stock_obj.candle_data if isinstance(stock_obj.candle_data, list) else []
            
            if not existing_data:
                # If no existing data, maybe fetch 3y for initialization (first time)
                # But user said "update ... recent 1 month", implying optimization for existing.
                # If truly empty, we might want to fetch more. 
                # Let's check if we should fallback to 3y if empty.
                # For safety, if empty, let's just fetch 3y once.
                hist_full = ticker.history(period="3y", interval="1wk")
                full_data = []
                for date, row in hist_full.iterrows():
                    ts = int(date.timestamp() * 1000)
                    full_data.append({
                        'x': ts,
                        'y': [row['Open'], row['High'], row['Low'], row['Close']]
                    })
                stock_obj.candle_data = full_data
            else:
                # Merger Strategy:
                # Create dict from existing by timestamp for easy lookup/overwrite
                data_map = {item['x']: item for item in existing_data}
                
                # Update with new data
                for item in new_data:
                    data_map[item['x']] = item
                
                # Convert back to list and sort
                merged_data = list(data_map.values())
                merged_data.sort(key=lambda k: k['x'])
                
                stock_obj.candle_data = merged_data

        except Exception as e:
            print(f"Error fetching history for {stock_obj.name}: {e}")

        stock_obj.save()
        return True
        
    except Exception as e:
        print(f"Generla error updating {stock_obj.name}: {e}")
        return False

import requests
from bs4 import BeautifulSoup

def get_naver_stock_name(code):
    """
    Naver 금융에서 종목명 크롤링 (실시간/정확)
    """
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        name_tag = soup.select_one('.wrap_company h2 a')
        if name_tag:
            return name_tag.text.strip()
            
        return None
    except Exception as e:
        print(f"Naver checking failed: {e}")
        return None

def get_naver_stock_extra_info(code, exchange=''):
    """
    Naver 금융에서 시가총액 및 기업개요 가져오기
    """
    data = {'market_cap': None, 'description': None}
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        # 해외 주식일 경우 (Naver 해외증권은 구조가 다름 -> 여기서는 국내 위주 혹은 해외는 Yahoo 사용)
        # Naver 해외 증권 URL 구조 확인 필요. 일단 국내만 시도.
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')

        # 1. Market Cap (시가총액)
        # <em id="_market_sum">367조 1,416</em>
        mkt_sum = soup.select_one('#_market_sum')
        if mkt_sum:
            # 367조 1,416 -> 숫자 변환
            # 조 단위 처리, 억 단위 처리
            txt = mkt_sum.text.strip().replace(',', '').replace('조', '').replace(' ', '')
            # "3671416" (억 단위) -> * 100,000,000
            try:
                data['market_cap'] = int(txt) * 100000000
            except:
                pass

        # 2. Description (기업개요)
        # <div class="summary_info"> <p> ... </p> </div>
        summary = soup.select_one('.summary_info p')
        if summary:
            data['description'] = summary.text.strip()
            
        return data
    except Exception as e:
        print(f"Naver extra info failed: {e}")
        return data
