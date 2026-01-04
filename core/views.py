import datetime
import re
import json  # [필수] JSON 데이터 처리를 위해 추가
from itertools import groupby
from operator import attrgetter

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Agent, Message, Organization, Approval, InvestmentLog, User
from .tasks import create_approval_draft

# [공통] 사이드바용 직원 목록 호출 함수
def get_sidebar_agents(user):
    if user.organization:
        return Agent.objects.filter(organization=user.organization)
    return Agent.objects.none()

# 1. 메인 홈
@login_required
def index(request):
    agents = get_sidebar_agents(request.user)
    return render(request, 'index.html', {'agents': agents})

# 2. 메신저
@login_required
def messenger(request, agent_id=None):
    user = request.user
    if not user.organization:
        return render(request, 'error.html', {'message': "소속된 회사가 없습니다."})
        
    agents = get_sidebar_agents(user)
    active_agent = None
    messages = []
    initial_greeting = ""

    if agent_id:
        active_agent = get_object_or_404(Agent, id=agent_id, organization=user.organization)
        messages = Message.objects.filter(user=user, agent=active_agent).order_by('created_at')

        now = datetime.datetime.now()
        hour = now.hour
        time_text = "좋은 아침입니다" if 5 <= hour < 11 else "점심 맛있게 드셨습니까" if 11 <= hour < 14 else "좋은 저녁입니다"
        initial_greeting = f"{time_text}, 사장님. {active_agent.department} {active_agent.name} {active_agent.position}입니다. 무엇을 도와드릴까요?"

        if request.method == 'POST':
            user_input = request.POST.get('message')
            if user_input:
                Message.objects.create(agent=active_agent, user=user, role='user', content=user_input)
                create_approval_draft.delay(user_input, active_agent.id, user.id, user.organization.id)
                return redirect('messenger', agent_id=agent_id)

    return render(request, 'messenger.html', {
        'agents': agents, 
        'active_agent': active_agent,
        'messages': messages,
        'initial_greeting': initial_greeting
    })

# 3. 투자 관리
@login_required
def investment_management(request):
    user = request.user
    agents = get_sidebar_agents(user)
    portfolio = InvestmentLog.objects.filter(agent__organization=user.organization, status='approved').order_by('-approved_at')
    drafts = Approval.objects.filter(organization=user.organization, report_type__in=['buy', 'sell'], status='pending').order_by('-created_at')

    return render(request, 'investment_management.html', {
        'agents': agents,
        'portfolio': portfolio,
        'drafts': drafts
    })

# 4. 전자결재함
@login_required
def approval_list(request):
    agents = get_sidebar_agents(request.user)
    approvals = Approval.objects.filter(organization=request.user.organization).order_by('-created_at')
    return render(request, 'approval_list.html', {'agents': agents, 'approvals': approvals})

# 5. 결재 상세
@login_required
def approval_detail(request, pk):
    user = request.user
    agents = get_sidebar_agents(user)
    approval = get_object_or_404(Approval, pk=pk, organization=user.organization)
    
    if request.method == 'POST':
        action = request.POST.get('action') 
        approval.title = request.POST.get('title', approval.title)
        approval.content = request.POST.get('content', approval.content)
        
        if action == 'approve':
            if approval.report_type in ['buy', 'sell']:
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

    return render(request, 'approval_detail.html', {'agents': agents, 'approval': approval})

# 6. 직접 기안 작성
@login_required
def create_self_approval(request):
    agents = get_sidebar_agents(request.user)
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
    return render(request, 'create_approval.html', {'agents': agents})

# 7. [수정됨] 조직도 (Google Charts 데이터 생성 로직)
@login_required
def org_chart(request):
    user = request.user
    agents = get_sidebar_agents(user)
    
    # Google Charts용 데이터 리스트 초기화
    # 형식: [ [{v:'id', f:'html'}, 'parent_id', 'tooltip'], ... ]
    chart_data = []

    # (1) CEO 노드 (Root)
    ceo = User.objects.filter(organization=user.organization, role='ceo').first()
    ceo_name = ceo.username if ceo else "CEO"
    ceo_id = "ceo_node"
    
    ceo_html = f"""
        <div class="node-card ceo-card">
            <div class="profile-icon">👑</div>
            <div class="node-name">{ceo_name}</div>
            <div class="node-role">CEO</div>
        </div>
    """
    chart_data.append([{'v': ceo_id, 'f': ceo_html}, '', 'CEO'])

    # (2) 부서 및 직원 노드
    agents_sorted = agents.order_by('department')
    
    for dept_name, members in groupby(agents_sorted, attrgetter('department')):
        # 2-1. 부서장(Division) 노드 -> CEO 밑에 연결
        dept_id = f"dept_{dept_name}"
        dept_html = f"""
            <div class="node-card dept-card">
                <div class="node-name">{dept_name}</div>
            </div>
        """
        chart_data.append([{'v': dept_id, 'f': dept_html}, ceo_id, dept_name])

        # 2-2. 직원 노드 -> 해당 부서장 밑에 연결
        for agent in members:
            agent_id = f"agent_{agent.id}"
            
            # 이미지 처리
            img_html = "🤖"
            if agent.profile_image:
                img_html = f"<img src='{agent.profile_image.url}' style='width:100%; height:100%; object-fit:cover;'>"
            
            agent_html = f"""
                <a href='/messenger/{agent.id}/' class='node-card agent-card'>
                    <div class='img-circle'>{img_html}</div>
                    <div class='node-name'>{agent.name}</div>
                    <div class='node-role'>{agent.position}</div>
                </a>
            """
            chart_data.append([{'v': agent_id, 'f': agent_html}, dept_id, agent.role])

    # JSON 변환 후 템플릿 전달
    return render(request, 'org_chart.html', {
        'agents': agents, 
        'chart_data': json.dumps(chart_data), 
        'org': user.organization
    })