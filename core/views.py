import datetime
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Agent, Message, Organization, Approval, InvestmentLog, User
from .tasks import create_approval_draft  # GPT-5 Nano 분석용 Celery 태스크

# 1. 메인 홈
@login_required
def index(request):
    return render(request, 'index.html')

# 2. 메신저 (시간대별 가변 인사말 + GPT-5 Nano 비동기 분석 연동)
@login_required
def messenger(request, agent_id=None):
    user = request.user
    if not user.organization:
        return render(request, 'error.html', {'message': "소속된 회사가 없습니다."})
        
    agents = Agent.objects.filter(organization=user.organization)
    active_agent = None
    messages = []
    initial_greeting = ""

    if agent_id:
        active_agent = get_object_or_404(Agent, id=agent_id, organization=user.organization)
        messages = Message.objects.filter(user=user, agent=active_agent).order_by('created_at')

        # --- [기존 유지] 시간대별 인사말 생성 로직 ---
        now = datetime.datetime.now()
        hour = now.hour

        if 5 <= hour < 11:
            time_text = "좋은 아침입니다, 사장님."
        elif 11 <= hour < 14:
            time_text = "점심 맛있게 드셨습니까, 사장님."
        else:
            time_text = "좋은 저녁입니다, 사장님."

        initial_greeting = f"{time_text} {active_agent.department} {active_agent.name} {active_agent.position}입니다. 무엇을 도와드릴까요?"
        # --------------------------------------------

        if request.method == 'POST':
            user_input = request.POST.get('message')
            if user_input:
                # 1. 사용자의 지시 메시지 저장
                Message.objects.create(agent=active_agent, user=user, role='user', content=user_input)
                
                # 2. [핵심] GPT-5 Nano 분석 및 기안 생성을 위해 Celery 비동기 작업 호출
                # 사장님의 짧은 지시를 전문 공문서로 바꾸는 작업은 background에서 수행됩니다.
                create_approval_draft.delay(user_input, active_agent.id, user.id, user.organization.id)
                
                return redirect('messenger', agent_id=agent_id)

    return render(request, 'messenger.html', {
        'agents': agents, 
        'active_agent': active_agent,
        'messages': messages,
        'initial_greeting': initial_greeting
    })

# 3. 투자 관리 및 포트폴리오 (승인된 내역 및 대기 중인 기안 확인)
@login_required
def investment_management(request):
    user = request.user
    # 최종 승인 완료되어 포트폴리오에 반영된 로그
    portfolio = InvestmentLog.objects.filter(
        agent__organization=user.organization, 
        status='approved'
    ).order_by('-approved_at')
    
    # 매수/매도 보고 중 결재 대기 중인 항목을 '기안 중'으로 표시
    drafts = Approval.objects.filter(
        organization=user.organization,
        report_type__in=['buy', 'sell'],
        status='pending'
    ).order_by('-created_at')

    return render(request, 'investment_management.html', {
        'portfolio': portfolio,
        'drafts': drafts
    })

# 4. 전자결재함 목록
@login_required
def approval_list(request):
    approvals = Approval.objects.filter(organization=request.user.organization).order_by('-created_at')
    return render(request, 'approval_list.html', {'approvals': approvals})

# 5. 결재 상세 (AI 분석 결과 수정 및 최종 승인 시 로그 생성)
@login_required
def approval_detail(request, pk):
    approval = get_object_or_404(Approval, pk=pk, organization=request.user.organization)
    
    if request.method == 'POST':
        action = request.POST.get('action') 
        # 사장님이 수정한 제목과 본문(AI 분석 내용)을 반영
        approval.title = request.POST.get('title', approval.title)
        approval.content = request.POST.get('content', approval.content)
        
        if action == 'approve':
            # [핵심] 결재 승인 시점에 매수/매도 보고인 경우만 실제 InvestmentLog 생성
            if approval.report_type in ['buy', 'sell']:
                # 매도의 경우 수량을 음수로 처리하여 포트폴리오 계산
                qty = int(approval.temp_quantity) if approval.report_type == 'buy' else -int(approval.temp_quantity)
                
                new_log = InvestmentLog.objects.create(
                    agent=approval.agent,
                    stock_code=approval.temp_stock_code,
                    total_amount=approval.temp_total_amount,
                    quantity=qty,
                    status='approved',
                    approved_at=timezone.now()
                )
                approval.investment_log = new_log
            
            approval.status = 'approved'
            approval.save()
            return redirect('approval_list')
            
        elif action == 'reject':
            approval.status = 'rejected'
            approval.save()
            return redirect('approval_list')

        approval.save()
        return redirect('approval_detail', pk=pk)

    return render(request, 'approval_detail.html', {'approval': approval})

# 6. 직접 기안 작성 (참고용)
@login_required
def create_self_approval(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        approval = Approval.objects.create(
            organization=request.user.organization,
            drafter=request.user,
            title=title,
            content=content,
            status='approved'
        )
        return redirect('approval_detail', pk=approval.id)
    return render(request, 'create_approval.html')

# 7. 조직도
@login_required
def org_chart(request):
    agents = Agent.objects.filter(organization=request.user.organization)
    return render(request, 'org_chart.html', {'agents': agents, 'org': request.user.organization})