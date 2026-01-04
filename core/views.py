import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Agent, Message, Organization, Approval
from .tasks import create_approval_draft

# 1. 메인 홈
@login_required
def index(request):
    return render(request, 'index.html')

# 2. 메신저 (시간대별 가변 인사말 로직 추가)
@login_required
def messenger(request, agent_id=None):
    user = request.user
    if not user.organization:
        return render(request, 'error.html', {'message': "소속된 회사가 없습니다."})
        
    agents = Agent.objects.filter(organization=user.organization)
    active_agent = None
    messages = []
    initial_greeting = "" # 첫 인사말 변수 초기화

    if agent_id:
        active_agent = get_object_or_404(Agent, id=agent_id, organization=user.organization)
        messages = Message.objects.filter(user=user, agent=active_agent).order_by('created_at')

        # --- [신규] 시간대별 인사말 생성 로직 ---
        now = datetime.datetime.now()
        hour = now.hour

        # 시간대 구분
        if 5 <= hour < 11:
            time_text = "좋은 아침입니다, 사장님."
        elif 11 <= hour < 14:
            time_text = "점심 맛있게 드셨습니까, 사장님."
        else:
            time_text = "좋은 저녁입니다, 사장님."

        # "부서명 이름 직급" 조합 (예: 배당금융실 드웨인 실장)
        initial_greeting = f"{time_text} {active_agent.department} {active_agent.name} {active_agent.position}입니다. 무엇을 도와드릴까요?"
        # ---------------------------------------

        if request.method == 'POST':
            user_input = request.POST.get('message')
            if user_input:
                # 1. 사용자의 메시지 저장
                Message.objects.create(agent=active_agent, user=user, role='user', content=user_input)
                
                # 2. Celery 비동기 작업 호출
                create_approval_draft.delay(user_input, active_agent.id, user.id, user.organization.id)
                
                return redirect('messenger', agent_id=agent_id)

    return render(request, 'messenger.html', {
        'agents': agents, 
        'active_agent': active_agent,
        'messages': messages,
        'initial_greeting': initial_greeting # 템플릿으로 인사말 전달
    })

# 3. 직접 기안 작성
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

# 4. 전자결재함
@login_required
def approval_list(request):
    approvals = Approval.objects.filter(organization=request.user.organization).order_by('-created_at')
    return render(request, 'approval_list.html', {'approvals': approvals})

# 5. 문서 상세 (수정 및 승인 로직)
@login_required
def approval_detail(request, pk):
    approval = get_object_or_404(Approval, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action') 
        new_content = request.POST.get('content')
        
        if new_content:
            approval.content = new_content
            
        if action == 'approve':
            approval.status = 'approved'
        
        approval.save()
        
        if action == 'approve':
            return redirect('approval_list')
        else:
            return redirect('approval_detail', pk=pk)

    return render(request, 'approval_detail.html', {'approval': approval})

# 6. 조직도
@login_required
def org_chart(request):
    agents = Agent.objects.filter(organization=request.user.organization)
    return render(request, 'org_chart.html', {'agents': agents, 'org': request.user.organization})