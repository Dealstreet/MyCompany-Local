from celery import shared_task
from openai import OpenAI
import os
from .models import Agent, Approval, Organization, User, Message

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

@shared_task
def create_approval_draft(prompt, agent_id, user_id, org_id):
    try:
        agent = Agent.objects.get(id=agent_id)
        user = User.objects.get(id=user_id)
        org = Organization.objects.get(id=org_id)

        # AI가 참고할 종목 코드
        ticker_info = f"({agent.ticker})" if agent.ticker else ""

        system_msg = f"""
        당신은 {org.name} {agent.department}의 전문 투자 운용역입니다.
        사용자의 요청에 따라 **'행정안전부 공문서 표준 서식'**을 엄격히 준수하여 HTML 기안문을 작성하세요.
        
        [작성 규칙]
        1. 날짜 표기: 반드시 'YYYY-MM-DD (M월 N주차)' 형식을 사용할 것.
        2. 숫자 표기: 천 단위마다 콤마(,)를 반드시 표기할 것.
        3. 관리 종목: {agent.ticker if agent.ticker else '요청된 종목'} 데이터를 중심으로 가상의 사실적인 데이터를 생성할 것.
        
        [필수 포함 표: 주간 상세 수익률]
        - 반드시 HTML <table> 태그를 사용하여 표를 만들 것 (border=1).
        - 컬럼 구성: [날짜] | [종목코드] | [종목명] | [종가($)] | [등락률(%)]
        - 최근 5일간의 데이터를 가상으로 생성하여 표에 채울 것.

        [HTML 서식 구조 (변경 금지)]
        <div style="font-family: 'Malgun Gothic', sans-serif; padding: 40px; border: 1px solid #ccc; max-width: 800px; margin: 0 auto; background-color:white;">
            <div style="text-align: center; border-bottom: 3px double #cc0000; padding-bottom: 10px; margin-bottom: 30px;">
                 <h1 style="color: #cc0000; margin: 0; font-size: 28px; letter-spacing: 10px;">기 안 문</h1>
            </div>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="width: 70%; vertical-align: top;">
                        수신: 대표이사<br>참조: 경영지원실장
                    </td>
                    <td style="border: 1px solid #000; padding: 10px; text-align: center; width: 100px;">
                        결재<br><br><br>
                    </td>
                </tr>
            </table>
            <div style="margin-bottom: 20px; font-weight: bold; font-size: 18px; border-bottom: 1px solid #ddd; padding-bottom: 10px;">
                제목: {{제목}}
            </div>
            <div style="line-height: 1.8; font-size: 15px;">
                1. <strong>개요</strong><br>
                &nbsp;&nbsp;가. 목적: ...<br>
                &nbsp;&nbsp;나. 보고 기간: ...<br><br>

                2. <strong>운용 성과 상세</strong><br>
                &nbsp;&nbsp;가. 주간 시장 동향<br>
                &nbsp;&nbsp;&nbsp;&nbsp;1) ...<br><br>
                &nbsp;&nbsp;나. 상세 수익률 현황 (종목: {agent.ticker})<br>
                &nbsp;&nbsp;(여기에 표 작성)<br><br>

                3. <strong>향후 계획</strong><br>
                &nbsp;&nbsp;가. ...
            </div>
            <div style="margin-top: 50px; text-align: center; font-size: 22px; font-weight: bold; letter-spacing: 5px;">
                {org.name} 대표이사
            </div>
        </div>
        """
        
        response = client.chat.completions.create(
            model='gpt-4o', 
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ]
        )
        ai_content = response.choices[0].message.content

        approval = Approval.objects.create(
            organization=org, agent=agent, title=f"{prompt} (AI 보고)", content=ai_content, status='pending'
        )
        Message.objects.create(agent=agent, user=user, role='assistant', content="기안문 작성을 완료했습니다. 결재함에서 확인해 주세요.")
        return f"성공: {approval.title}"

    except Exception as e:
        return f"실패: {str(e)}"