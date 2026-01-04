from celery import shared_task
from openai import OpenAI
import os
import re
from django.utils import timezone
from .models import Agent, Approval, Organization, User, Message

# OpenAI 클라이언트 설정 (GPT-5 Nano 모델 사용 가정)
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

@shared_task
def create_approval_draft(prompt, agent_id, user_id, org_id):
    try:
        agent = Agent.objects.get(id=agent_id)
        user = User.objects.get(id=user_id)
        org = Organization.objects.get(id=org_id)

        # 1. 보고 유형 감지
        report_type = 'gen'
        if '[매수]' in prompt: report_type = 'buy'
        elif '[매도]' in prompt: report_type = 'sell'
        elif '[성과]' in prompt: report_type = 'perf'
        elif '[시장]' in prompt: report_type = 'market'

        # 2. AI 분석 프롬프트 구성 (GPT-5 Nano 페르소나 부여)
        system_msg = f"""
        당신은 {org.name} {agent.department} 소속 투자 전문가 {agent.name} {agent.position}입니다.
        모델명 'GPT-5 Nano'의 고성능 분석 능력을 발휘하여 사용자의 지시를 바탕으로 전문적인 공문서 본문을 작성하세요.

        [작성 규칙]
        - 말투: "하였습니다", "바랍니다" 등 격식 있는 공문서 종결 어미 사용.
        - 인사말: 내부 결재 문서이므로 "귀하의 무궁한 발전..." 등 외부 인사말은 절대 사용 금지.
        - 항목 체계: 1. 가. 1) 가) 순서를 엄격히 준수.
        - 핵심 미션: 사용자가 입력한 짧은 데이터({prompt})를 바탕으로, '매수 이유', '성과 원인 분석', '시장 향후 전망' 등을 전문가 관점에서 풍성하게 서술할 것.

        [보고 유형별 필수 서술 내용]
        1. 매수/매도: 해당 종목의 기술적/기본적 분석에 근거한 매매 사유.
        2. 성과: 기간 내 수익률 발생의 거시적 변수 및 종목 특이사항 분석.
        3. 시장: 현재 지표의 의미와 당사 포트폴리오에 미칠 영향 평가.
        """

        response = client.chat.completions.create(
            model='gpt-4o', # 실제 환경에선 존재하는 모델명 사용, 페르소나로 GPT-5 Nano 부여
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"다음 데이터를 바탕으로 공문서 본문을 전문적으로 작성하라: {prompt}"}
            ]
        )
        ai_analysis = response.choices[0].message.content

        # 3. 데이터 파싱 (임시 필드 저장을 위한 정규식)
        temp_data = {
            'stock': re.search(r'종목:([\w:]+)', prompt).group(1) if '종목:' in prompt else agent.ticker,
            'qty': re.search(r'수량:(\d+)', prompt).group(1) if '수량:' in prompt else 0,
            'amt': re.search(r'총액:(\d+)', prompt).group(1) if '총액:' in prompt else 0,
            'date': re.search(r'일자:([\d-]+)', prompt).group(1) or re.search(r'거래일:([\d-]+)', prompt).group(1) if '일자:' in prompt or '거래일:' in prompt else None
        }

        # 4. 결재 문서 생성
        approval = Approval.objects.create(
            organization=org,
            agent=agent,
            report_type=report_type,
            temp_stock_code=temp_data['stock'],
            temp_quantity=temp_data['qty'],
            temp_total_amount=temp_data['amt'],
            temp_date=temp_data['date'],
            title=f"[{dict(Approval.REPORT_TYPES)[report_type]}] {temp_data['stock']} 관련 보고",
            content=ai_analysis, # AI가 작성한 전문 분석 내용 저장
            status='pending'
        )

        # 5. 메신저 피드백
        Message.objects.create(
            agent=agent, user=user, role='assistant', 
            content=f"사장님, GPT-5 Nano 분석을 통해 '{approval.title}' 기안 작성을 완료했습니다. 전자결재함을 확인해 주십시오."
        )

        return f"성공: {approval.id}"

    except Exception as e:
        return f"실패: {str(e)}"