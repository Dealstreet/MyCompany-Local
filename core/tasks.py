from celery import shared_task
from openai import OpenAI
import os
import re
from django.utils import timezone
from .models import Agent, Approval, Organization, User, Message

# OpenAI 클라이언트 설정
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# [헬퍼 1] 문자열 파싱 (종목, 날짜용) - 있는 그대로 추출
def safe_parse_str(pattern, text, default=None):
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return default

# [헬퍼 2] 숫자 파싱 (수량, 금액용) - 쉼표, 단위 제거 후 정수 변환
def safe_parse_int(pattern, text, default=0):
    match = re.search(pattern, text)
    if match:
        val = match.group(1)
        # 쉼표(,), 원, 주, 공백을 모두 제거
        clean_val = val.replace(',', '').replace('원', '').replace('주', '').strip()
        try:
            return int(clean_val) # 정수로 변환 ('35,000' -> 35000)
        except ValueError:
            return default
    return default

@shared_task
def create_approval_draft(prompt, agent_id, user_id, org_id, temp_msg_id):
    try:
        # 1. DB 객체 조회
        agent = Agent.objects.get(id=agent_id)
        user = User.objects.get(id=user_id)
        org = Organization.objects.get(id=org_id)
        
        # 임시 메시지 가져오기
        temp_msg = Message.objects.get(id=temp_msg_id)

        # 2. 보고 유형 감지
        report_type = 'gen'
        if '[매수]' in prompt: report_type = 'buy'
        elif '[매도]' in prompt: report_type = 'sell'
        elif '[성과]' in prompt: report_type = 'perf'
        elif '[시장]' in prompt: report_type = 'market'

        # 3. AI 분석 (GPT-5 Nano 페르소나)
        system_msg = f"""
        당신은 {org.name} {agent.department} 소속 투자 전문가 {agent.name} {agent.position}입니다.
        사용자의 지시를 바탕으로 '행정안전부 공문서 표준 서식'에 맞춘 전문적인 기안문 본문을 작성하세요.
        
        [작성 규칙]
        - 말투: "~하였습니다", "~바랍니다" 등 격식체 사용.
        - 내용: {prompt}에 포함된 데이터를 바탕으로 매수 사유, 성과 원인, 시장 전망 등을 전문가 관점에서 풍성하게 서술.
        - 항목 구분: 1. 가. 1) 가) 순서 준수.
        """

        response = client.chat.completions.create(
            model='gpt-5-nano', 
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"다음 지시를 바탕으로 공문서 본문을 작성하라: {prompt}"}
            ]
        )
        ai_analysis = response.choices[0].message.content

        # 4. 데이터 파싱 (분리된 함수 사용으로 안전성 확보)
        
        # (1) 종목코드: 문자열 그대로 가져옴
        stock = safe_parse_str(r'종목:([\w:]+)', prompt, default=agent.ticker)
        
        # (2) 수량: '1,000주', '1000' 모두 1000(int)으로 변환
        qty = safe_parse_int(r'수량:\s*([\d,]+[주]?)', prompt, default=0)
        
        # (3) 금액: '35,000원', '35000' 모두 35000(int)으로 변환
        amt = safe_parse_int(r'총액:\s*([\d,]+[원]?)', prompt, default=0)
        
        # (4) 날짜: 문자열 그대로 가져옴 ('일자' 없으면 '거래일' 체크)
        date_str = safe_parse_str(r'일자:\s*([\d-]+)', prompt)
        if not date_str:
            date_str = safe_parse_str(r'거래일:\s*([\d-]+)', prompt)

        # 5. 결재 문서 생성
        approval = Approval.objects.create(
            organization=org,
            agent=agent,
            report_type=report_type,
            temp_stock_code=stock,
            temp_quantity=qty,
            temp_total_amount=amt,
            temp_date=date_str, 
            title=f"[{dict(Approval.REPORT_TYPES).get(report_type, '일반')}] {stock if stock else '보고'} 건",
            content=ai_analysis,
            status='pending'
        )

        # 6. 임시 메시지 내용 업데이트 (금액에 콤마 포맷팅 적용하여 사용자에게 보여줌)
        temp_msg.content = f"사장님, 요청하신 안건에 대해 '{approval.title}' 기안 작성을 완료했습니다.\n(금액: {amt:,}원 / 수량: {qty:,}주)\n결재함에서 상세 내용을 확인해 주세요."
        temp_msg.save()

        return f"성공: {approval.id}"

    except Exception as e:
        # 에러 발생 시 사용자에게 알림
        try:
            temp_msg = Message.objects.get(id=temp_msg_id)
            temp_msg.content = f"죄송합니다. 처리 중 오류가 발생했습니다.\n오류 내용: {str(e)}"
            temp_msg.save()
        except:
            pass
        return f"실패: {str(e)}"