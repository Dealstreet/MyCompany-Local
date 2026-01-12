import re
from django.utils import timezone
from django.db.models import Max
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
