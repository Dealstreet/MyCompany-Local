import datetime
import re
import json
from itertools import groupby
from operator import attrgetter

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime

from .models import Agent, Message, Organization, Approval, InvestmentLog, User, UserProfile, Department
from .utils import parse_mirae_sms
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

@login_required
def org_chart(request):
    user = request.user
    agents = get_sidebar_agents(user)
    
    chart_data = []
    
    # 1. CEO (최상위)
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

    # 2. 부서 (Department) 가져오기
    departments = Department.objects.filter(organization=user.organization).order_by('id')
    
    # 부서 노드 생성 및 부서ID 매핑 (이름 -> ID)
    dept_id_map = {} # 부서명 -> 부서노드ID

    for dept in departments:
        node_id = f"dept_{dept.id}"
        dept_id_map[dept.name] = node_id
        
        # 상위 부서 연결
        if dept.parent:
            parent_id = f"dept_{dept.parent.id}"
        else:
            parent_id = ceo_id # 상위가 없으면 CEO 직속 (즉, 본부)

        # 스타일: 상위 부서가 없으면(본부) 배경색 다르게
        bg_style = 'background:#001f3f; font-weight:800; color:#ffffff;' if not dept.parent else ''
        
        dept_html = f"""
            <div class="node-card dept-card" style="{bg_style}">
                <div class="node-name">{dept.name}</div>
            </div>
        """
        chart_data.append([{'v': node_id, 'f': dept_html}, parent_id, dept.name])

    # 3. 직원 (Agents) 배치
    for agent in agents:
        agent_id = f"agent_{agent.id}"
        
        # 부모 노드 결정: Agent.department_obj (FK)를 사용
        if agent.department_obj:
            parent_node = f"dept_{agent.department_obj.id}"
        else:
            # 연결된 부서가 없으면 CEO 직속 (혹은 예외 처리)
            parent_node = ceo_id
        
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
        chart_data.append([{'v': agent_id, 'f': agent_html}, parent_node, agent.role])

    return render(request, 'org_chart.html', {
        'agents': agents, 
        'chart_data': json.dumps(chart_data), 
        'org': user.organization
    })
# 2. [수정됨] 메신저 (멈춘 메시지 강제 종료 기능 추가)
@login_required
def messenger(request, agent_id=None):
    user = request.user
    if not user.organization:
        return render(request, 'error.html', {'message': "소속된 회사가 없습니다."})
    
    # [핵심 추가] 1분 이상 '처리 중' 상태로 멈춰있는 좀비 메시지 강제 종료
    # 페이지를 열 때마다 자동으로 체크해서 멈춘 녀석들을 정리합니다.
    try:
        limit_time = timezone.now() - datetime.timedelta(minutes=1)
        stuck_msgs = Message.objects.filter(
            user=user,
            content='[PROCESSING]',
            created_at__lt=limit_time
        )
        # 멈춘 메시지 내용 변경
        stuck_msgs.update(content="⚠️ 시스템 오류로 인해 처리가 중단되었습니다. 다시 지시해 주세요.")
    except Exception as e:
        print(f"메시지 정리 중 오류: {e}")

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
        dept_name = active_agent.department_obj.name if active_agent.department_obj else "소속미정"
        initial_greeting = f"{time_text}, 사장님. {dept_name} {active_agent.name} {active_agent.position}입니다. 무엇을 도와드릴까요?"

        if request.method == 'POST':
            user_input = request.POST.get('message')
            if user_input:
                Message.objects.create(agent=active_agent, user=user, role='user', content=user_input)
                
                # 임시 메시지 생성
                temp_msg = Message.objects.create(
                    agent=active_agent, 
                    user=user, 
                    role='assistant', 
                    content="[PROCESSING]" 
                )
                
                # Celery 태스크 호출 (인자 5개)
                create_approval_draft.delay(user_input, active_agent.id, user.id, user.organization.id, temp_msg.id)
                
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
    
    # 1. 포트폴리오 (현재 보유 중인 종목) - 페이지네이션 적용 (5개)
    # [수정] 내 회사 소속이거나(AI), 내가 직접 한(Real) 거래
    portfolio_qs = InvestmentLog.objects.filter(
        Q(agent__organization=user.organization) | Q(user__organization=user.organization), 
        status='approved'
    ).order_by('-approved_at')
    
    pf_paginator = Paginator(portfolio_qs, 5)
    pf_page_number = request.GET.get('pf_page')
    portfolio = pf_paginator.get_page(pf_page_number)
    
    # [추가] 재무 현황 요약 데이터 계산 (전체 데이터 기준)
    # 페이지네이션 된 portfolio 객체가 아닌 전체 쿼리셋을 사용해야 정확한 총액 계산 가능
    summary_portfolio = InvestmentLog.objects.filter(
        Q(agent__organization=user.organization) | Q(user__organization=user.organization), 
        status='approved'
    )
    
    total_buy_amount = 0
    total_count = summary_portfolio.count()
    for item in summary_portfolio:
        total_buy_amount += item.total_amount

    # 2. 결재 대기 목록
    drafts = Approval.objects.filter(
        organization=user.organization,
        report_type__in=['buy', 'sell'],
        status='pending'
    ).order_by('-created_at')

    # 3. [추가] 운용 로그 (페이지네이션 적용)
    # status가 approved인 것만 가져옴
    log_list = InvestmentLog.objects.filter(
        Q(agent__organization=user.organization) | Q(user__organization=user.organization),
        status='approved'
    ).order_by('-approved_at')
    
    paginator = Paginator(log_list, 5) # 페이지당 5개 표시
    page_number = request.GET.get('page')
    investment_logs = paginator.get_page(page_number)

    # AJAX 요청 처리 (섹션별 페이지네이션)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        section = request.GET.get('section')
        if section == 'portfolio':
             return render(request, 'partials/portfolio_section.html', {'portfolio': portfolio})
        else:
             return render(request, 'partials/log_section.html', {'investment_logs': investment_logs})

    # 4. 재무 현황 요약 데이터 계산
    # (실제 주가 데이터가 연동되면 current_price를 반영해야 하지만, 지금은 매수가 기준으로 계산)
    # 위에서 이미 계산함 (summary_portfolio 사용)
    
    # 가상의 수익률 시뮬레이션 (추후 주가 API 연동 시 교체)

    # 가상의 수익률 시뮬레이션 (추후 주가 API 연동 시 교체)
    # 현재는 원금 = 평가액으로 설정 (수익률 0%)
    summary = {
        'count': total_count,
        'total_buy': total_buy_amount,         # 총 매수금액 (현재 보유분)
        'total_sell': 0,                       # 총 매도금액 (실현손익 로그 연동 필요)
        'principal': total_buy_amount,         # 원금
        'eval_balance': total_buy_amount,      # 평가잔액 (현재가 * 수량)
        'yield': 0.0,                          # 수익률
        'yield_color': 'text-dark'             # 수익률 색상 (빨강/파랑)
    }

    return render(request, 'investment_management.html', {
        'agents': agents,
        'portfolio': portfolio,
        'drafts': drafts,
        'investment_logs': investment_logs, # [추가] 로그 전달
        'summary': summary
    })

# 4. 전자결재함
@login_required
def approval_list(request):
    agents = get_sidebar_agents(request.user)
    
    # 1. URL에서 필터 조건 가져오기 (기본값: 'all')
    status_filter = request.GET.get('status', 'all')
    
    # 2. 기본 쿼리셋 (전체)
    approvals = Approval.objects.filter(organization=request.user.organization)
    
    # 3. 필터링 적용
    if status_filter == 'pending':
        approvals = approvals.filter(status='pending')
    elif status_filter == 'approved':
        approvals = approvals.filter(status='approved')
    elif status_filter == 'rejected':
        approvals = approvals.filter(status='rejected')
    
    # 최신순 정렬
    approvals = approvals.order_by('-created_at')

    return render(request, 'approval_list.html', {
        'agents': agents, 
        'approvals': approvals,
        'current_status': status_filter # 탭 활성화를 위해 현재 상태 전달
    })

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
                    stock_name=approval.temp_stock_name, # [추가] 종목명 저장
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

# 7. 조직도 (Google Charts용)


@method_decorator(csrf_exempt, name='dispatch')
class SmsWebhookView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            secret_key = data.get('secret_key')
            
            # 인증
            try:
                profile = UserProfile.objects.get(secret_key=secret_key)
                user = profile.user
            except UserProfile.DoesNotExist:
                return JsonResponse({'status': 'fail', 'msg': 'Invalid Key'}, status=403)

            # 파싱
            parsed_data = parse_mirae_sms(data.get('sms_content'))
            if not parsed_data:
                return JsonResponse({'status': 'fail', 'msg': 'Parsing Failed'}, status=400)

            # 시간 처리
            if data.get('received_at'):
                trade_date = parse_datetime(data.get('received_at'))
            else:
                trade_date = timezone.now()

            # [핵심 변경] InvestmentLog에 저장 (통합)
            # 주문번호(order_no)가 이미 있으면 저장하지 않음 (get_or_create)
            obj, created = InvestmentLog.objects.get_or_create(
                order_no=parsed_data['order_no'],
                defaults={
                    'user': user,          # 사용자 연결
                    'agent': None,         # AI가 아님
                    'source': 'real',      # <--- 출처: 실거래
                    'status': 'approved',  # 이미 체결된 건이므로 승인 상태
                    
                    'stock_name': parsed_data.get('stock_name', 'Unknown'),
                    'stock_code': parsed_data.get('stock_code', ''),
                    'quantity': parsed_data.get('quantity', 0) if parsed_data.get('trade_type', '매수') == '매수' else -parsed_data.get('quantity', 0),
                    'total_amount': parsed_data.get('price', 0) * parsed_data.get('quantity', 0), # 총액 계산
                    'approved_at': trade_date # 체결 시간
                }
            )

            if created:
                return JsonResponse({'status': 'success', 'msg': 'Saved to InvestmentLog'})
            else:
                return JsonResponse({'status': 'exist', 'msg': 'Already exists'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)