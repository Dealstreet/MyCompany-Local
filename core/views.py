from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Agent, Message, Organization, Approval
from .tasks import create_approval_draft

# 1. 메인 홈
@login_required
def index(request):
    return render(request, 'index.html')

# 2. 메신저 (AI 직원 정보 전달 로직 강화)
@login_required
def messenger(request, agent_id=None):
    user = request.user
    if not user.organization:
        return render(request, 'error.html', {'message': "소속된 회사가 없습니다."})
        
    # 사용자의 조직에 속한 AI 직원들만 가져옴 (사이드바용)
    agents = Agent.objects.filter(organization=user.organization)
    active_agent = None
    messages = []

    if agent_id:
        # 선택된 AI 직원의 상세 정보를 가져옴
        active_agent = get_object_or_404(Agent, id=agent_id, organization=user.organization)
        messages = Message.objects.filter(user=user, agent=active_agent).order_by('created_at')

        if request.method == 'POST':
            # 템플릿의 input name을 'message'로 가정합니다.
            user_input = request.POST.get('message')
            if user_input:
                # 1. 사용자의 메시지 저장
                Message.objects.create(agent=active_agent, user=user, role='user', content=user_input)
                
                # 2. Celery 비동기 작업 호출 (AI 답변 및 기안문 작성)
                create_approval_draft.delay(user_input, active_agent.id, user.id, user.organization.id)
                
                return redirect('messenger', agent_id=agent_id)

    return render(request, 'messenger.html', {
        'agents': agents, 
        'active_agent': active_agent, # 템플릿에서 {{ active_agent }}로 사용
        'messages': messages
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