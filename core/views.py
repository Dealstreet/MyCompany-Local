from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Agent, Message, Organization, Approval
from .tasks import create_approval_draft

# 1. 메인 홈
def index(request):
    return render(request, 'index.html')

# 2. 메신저
@login_required
def messenger(request, agent_id=None):
    user = request.user
    if not user.organization:
        return render(request, 'error.html', {'message': "소속된 회사가 없습니다."})
        
    agents = Agent.objects.filter(organization=user.organization)
    active_agent = None
    messages = []

    if agent_id:
        active_agent = get_object_or_404(Agent, id=agent_id)
        messages = Message.objects.filter(user=user, agent=active_agent)

        if request.method == 'POST':
            prompt = request.POST.get('prompt')
            if prompt:
                Message.objects.create(agent=active_agent, user=user, role='user', content=prompt)
                create_approval_draft.delay(prompt, active_agent.id, user.id, user.organization.id)
                return redirect('messenger', agent_id=agent_id)

    return render(request, 'messenger.html', {'agents': agents, 'active_agent': active_agent, 'messages': messages})

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

# 5. 문서 상세 (수정 로직 추가)
@login_required
def approval_detail(request, pk):
    approval = get_object_or_404(Approval, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action') # 버튼의 value 값 확인
        new_content = request.POST.get('content')
        
        if new_content:
            approval.content = new_content
            
        if action == 'approve':
            approval.status = 'approved' # 승인 처리
        # action == 'save'일 경우 status는 그대로 두고 내용만 저장
        
        approval.save()
        
        if action == 'approve':
            return redirect('approval_list')
        else:
            return redirect('approval_detail', pk=pk) # 저장 후 현재 페이지 유지

    return render(request, 'approval_detail.html', {'approval': approval})

# 6. 조직도
@login_required
def org_chart(request):
    agents = Agent.objects.filter(organization=request.user.organization)
    return render(request, 'org_chart.html', {'agents': agents, 'org': request.user.organization})