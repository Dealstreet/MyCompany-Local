import datetime
import re
import json
import yfinance as yf
from itertools import groupby
from operator import attrgetter
from django.db.models import Q, Sum, F
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages # [Fix] Import messages
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from datetime import datetime, time
from django.http import JsonResponse, HttpResponse

from .models import User, Organization, Department, DailySnapshot, Transaction, Stock, InterestStock, Agent, Message, Approval, InvestmentLog, Account, TradeNotification, UserFavorite, PortfolioDisclosure, Post, Follow
from .forms import AgentForm, UserChangeForm, OrganizationForm
from .services import TransactionService, FinancialService
from .tasks import create_approval_draft, create_daily_snapshot
from .utils import parse_mirae_sms, format_approval_content, get_agent_by_stock

COUNTRY_MAP = {
    'South Korea': '한국',
    'United States': '미국',
    'Japan': '일본',
    'China': '중국',
    'Hong Kong': '홍콩',
    'Taiwan': '대만',
}

def identify_stock_country(ticker_symbol, info):
    """
    Robustly identify stock country using yf.info and ticker suffix
    """
    # 1. Try metadata
    country_en = info.get('country', '')
    if country_en:
        return COUNTRY_MAP.get(country_en, country_en)
    
    # 2. Suffix check
    if ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ'):
        return "한국"
    
    # [Fix] 6-digit code is Korean (e.g. 000660)
    if ticker_symbol.isdigit() and len(ticker_symbol) == 6:
        return "한국"
    
    # 3. No suffix (usually US)
    if '.' not in ticker_symbol:
        return "미국"
        
    # 4. Exchange check
    exchange = info.get('exchange', '')
    if exchange in ['NMS', 'NYQ', 'ASE', 'NGM', 'NCM', 'PCX']:
        return "미국"
    elif exchange in ['KSC', 'KOE']:
        return "한국"
        
    return ""

def get_sidebar_agents(user):
    if user.organization:
        return Agent.objects.filter(organization=user.organization)
    return Agent.objects.none()

@login_required
def index(request):
    agents = get_sidebar_agents(request.user)
    if request.method == 'POST':
        principles = request.POST.get('principles', '')
        request.user.principles = principles
        request.user.save()
        messages.success(request, "나의 원칙이 저장되었습니다.")
        return redirect('index')

    today = timezone.now().date()
    
    # [Favorites Logic]
    favorites = UserFavorite.objects.filter(user=request.user)
    
    return render(request, 'index.html', {
        'agents': agents,
        'today': today,
        'favorites': favorites,
        'active_main_menu': 'home',
        'active_sub_menu': 'home'
    })

@login_required
def org_chart(request):
    # Retrieve organization and agents
    organization = request.user.organization
    agents = Agent.objects.filter(organization=organization)
    
    # ... logic ...
    
    return render(request, 'org_chart.html', {
        'organization': organization,
        'departments': [], # If needed
        'agents': agents,
        'active_main_menu': 'organization', # Changed from 'home'
        'active_sub_menu': 'org'
    })

# ==========================================
# [New] Organization Management (Agent CRUD)
# ==========================================
@login_required
def agent_management(request):
    agents = Agent.objects.filter(organization=request.user.organization).select_related('department_obj')
    return render(request, 'agent_management.html', {
        'agents': agents,
        'active_main_menu': 'organization',
        'active_sub_menu': 'agents'
    })

@login_required
def agent_create(request):
    if request.method == 'POST':
        form = AgentForm(request.POST, request.FILES)
        if form.is_valid():
            agent = form.save(commit=False)
            agent.organization = request.user.organization
            agent.save()
            messages.success(request, f"{agent.name} 직원이 등록되었습니다.")
            return redirect('agent_management')
    else:
        form = AgentForm(initial={'organization': request.user.organization})
    
    return render(request, 'agent_form.html', {
        'form': form,
        'title': '직원 등록',
        'active_main_menu': 'organization',
        'active_sub_menu': 'agents'
    })

@login_required
def agent_edit(request, pk):
    agent = get_object_or_404(Agent, pk=pk, organization=request.user.organization)
    if request.method == 'POST':
        form = AgentForm(request.POST, request.FILES, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, f"{agent.name} 정보가 수정되었습니다.")
            return redirect('agent_management')
    else:
        form = AgentForm(instance=agent)
        
    return render(request, 'agent_form.html', {
        'form': form,
        'title': '직원 정보 수정',
        'agent': agent,
        'active_main_menu': 'organization',
        'active_sub_menu': 'agents'
    })

@login_required
def agent_delete(request, pk):
    agent = get_object_or_404(Agent, pk=pk, organization=request.user.organization)
    if request.method == 'POST':
        agent.delete()
        messages.success(request, f"{agent.name} 직원이 삭제되었습니다.")
        return redirect('agent_management')
    return redirect('agent_management')


# [New] Favorites APIs
@login_required
def add_favorite(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        url_name = request.POST.get('url_name')
        icon = request.POST.get('icon', '📌')
        
        # Limit check
        if UserFavorite.objects.filter(user=request.user).count() >= 5:
            messages.error(request, "즐겨찾기는 최대 5개까지만 등록 가능합니다.")
        else:
            UserFavorite.objects.create(user=request.user, name=name, url_name=url_name, icon=icon, display_order=999)
            messages.success(request, "즐겨찾기가 추가되었습니다.")
            
    return redirect('index')

@login_required
def delete_favorite(request, pk):
    fav = get_object_or_404(UserFavorite, pk=pk, user=request.user)
    fav.delete()
    messages.success(request, "즐겨찾기가 삭제되었습니다.")
    return redirect('index')

@csrf_exempt
@login_required
def update_favorite_order(request):
    """
    AJAX Endpoint to reorder favorites.
    Expects JSON: { "order": [id1, id2, id3, ...] }
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            order_list = data.get('order', [])
            
            for index, fav_id in enumerate(order_list):
                UserFavorite.objects.filter(id=fav_id, user=request.user).update(display_order=index)
                
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'invalid method'}, status=405)

# ==========================================
# [New] Master Dashboard (Superuser Only)
# ==========================================
@user_passes_test(lambda u: u.is_superuser)
def master_user_list(request):
    users = User.objects.all().select_related('organization').order_by('-date_joined')
    return render(request, 'master/user_list.html', {
        'users': users,
        'active_main_menu': 'master', # For highlighting if we add master menu later
    })

@user_passes_test(lambda u: u.is_superuser)
def master_user_toggle_status(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        # Prevent disabling self
        if user_obj == request.user:
            messages.error(request, "자신의 계정은 비활성화할 수 없습니다.")
        else:
            user_obj.is_active = not user_obj.is_active
            user_obj.save()
            status_msg = "활성화" if user_obj.is_active else "비활성화(정지)"
            messages.success(request, f"{user_obj.username} 계정이 {status_msg} 처리되었습니다.")
            
    return redirect('master_user_list')


@login_required
def messenger(request, agent_id=None):
    user = request.user
    agents = get_sidebar_agents(user)
    
    # [Mod] Remove auto-redirect. If no agent_id, show list.
    # if not agent_id and agents.exists():
    #     return redirect('messenger', agent_id=agents.first().id)
        
    active_agent = get_object_or_404(Agent, id=agent_id) if agent_id else None
    
    messages_list = []
    if active_agent:
        messages_list = Message.objects.filter(
            agent=active_agent, 
            user=user
        ).order_by('created_at')

    initial_greeting = "안녕하세요."
    if active_agent:
        hour = datetime.now().hour
        time_text = "좋은 아침입니다" if 5 <= hour < 11 else "점심 맛있게 드셨습니까" if 11 <= hour < 14 else "좋은 저녁입니다"
        dept_name = active_agent.department_obj.name if active_agent.department_obj else "소속미정"
        initial_greeting = f"{time_text}, 사장님. {dept_name} {active_agent.name} {active_agent.position}입니다. 무엇을 도와드릴까요?"

        if request.method == 'POST':
            user_input = request.POST.get('message')
            if user_input:
                Message.objects.create(agent=active_agent, user=user, role='user', content=user_input)
                
                temp_msg = Message.objects.create(
                    agent=active_agent, 
                    user=user, 
                    role='assistant', 
                    content="[PROCESSING]" 
                )
                
                create_approval_draft.delay(user_input, active_agent.id, user.id, user.organization.id, temp_msg.id)
                return redirect('messenger', agent_id=agent_id)

    return render(request, 'messenger.html', {
        'agents': agents, 
        'active_agent': active_agent,
        'messages': messages_list,
        'initial_greeting': initial_greeting,
        'active_main_menu': 'home',
        'active_sub_menu': 'messenger'
    })

@login_required
def investment_management(request):
    user = request.user
    agents = get_sidebar_agents(user)
    
    # 1. 포트폴리오 (Aggregation from Transactions)
    # Replaces simple InvestmentLog list with aggregated Portfolio Holdings
    portfolio_map = {}
    txs = Transaction.objects.filter(
        organization=user.organization, 
        related_asset__isnull=False
    ).select_related('related_asset').order_by('timestamp')

    for tx in txs:
        sid = tx.related_asset.id
        if sid not in portfolio_map:
            portfolio_map[sid] = {
                'stock': tx.related_asset,
                'stock_name': tx.related_asset.name,
                'stock_code': tx.related_asset.code,
                'quantity': 0,
                'total_amount': 0,
                'avg_price': 0,
                'approved_at': tx.timestamp # Init with first found
            }
        
        p = portfolio_map[sid]
        p['approved_at'] = tx.timestamp # Update to latest
        
        if tx.transaction_type == 'BUY':
            # Update Avg Price (Weighted Average)
            new_qty = tx.quantity
            cost = abs(tx.amount) - tx.fee # Principal
            
            # (Old Cost + New Cost) / Total Qty
            current_val = p['quantity'] * p['avg_price']
            total_qty = p['quantity'] + new_qty
            
            if total_qty > 0:
                p['avg_price'] = (current_val + cost) / total_qty
            else:
                p['avg_price'] = 0
            
            p['quantity'] += new_qty
            p['total_amount'] += cost
            
        elif tx.transaction_type == 'SELL':
            # Reduce Quantity, Avg Price stays same
            qty_sold = abs(tx.quantity)
            p['quantity'] -= qty_sold
            
            # Reduce allocated cost basis
            cost_removed = qty_sold * p['avg_price']
            p['total_amount'] -= cost_removed

    # [Removed nested get_stock_detail]
            
    # Convert to list and filter zero holdings
    portfolio_list = []
    for sid, p in portfolio_map.items():
        if p['quantity'] > 0:
            stock = p['stock']
            # Fetch Current Price
            cur_price = stock.current_price
            if not cur_price:
                # Fallback check
                 cur_price = 0
            
            p['current_price'] = cur_price
            p['eval_amount'] = cur_price * p['quantity']
            
            # Yield
            if p['total_amount'] > 0:
                 p['yield'] = ((p['eval_amount'] - p['total_amount']) / p['total_amount']) * 100
            else:
                 p['yield'] = 0
                 
            portfolio_list.append(p)
            
    # Pagination
    pf_paginator = Paginator(portfolio_list, 5)
    pf_page_number = request.GET.get('pf_page')
    portfolio = pf_paginator.get_page(pf_page_number)
    
    # Summary Calculation
    total_eval_amount = sum(p['eval_amount'] for p in portfolio_list)
    total_buy_amount = sum(p['total_amount'] for p in portfolio_list)
    
    # Calculate Total Sell Amount from Transactions
    total_sell_amount = Transaction.objects.filter(
        organization=user.organization,
        transaction_type='SELL'
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    # Note: Sell amount in DB is positive (Revenue). No modification needed.
    
    total_yield = 0
    if total_buy_amount > 0:
        total_yield = ((total_eval_amount - total_buy_amount) / total_buy_amount) * 100

    yield_color = 'text-success' if total_yield >= 0 else 'text-orange'
    if total_yield == 0: yield_color = 'text-dark'
    
    summary = {
        'count': len(portfolio_list),
        'total_buy': total_buy_amount,
        'total_sell': total_sell_amount,
        'eval_balance': total_eval_amount, # Renamed label in Template, variable kept for compatibility
        'yield': round(total_yield, 2),
        'yield_color': yield_color
    }

    # 2. 결재 대기 목록
    drafts = Approval.objects.filter(
        organization=user.organization,
        report_type__in=['buy', 'sell'],
        status='pending'
    ).order_by('-created_at')

    # 3. 운용 로그
    log_list = InvestmentLog.objects.filter(
        Q(agent__organization=user.organization) | Q(user__organization=user.organization),
        status='approved'
    ).order_by('-approved_at')
    
    paginator = Paginator(log_list, 5)
    page_number = request.GET.get('page')
    investment_logs = paginator.get_page(page_number)

    # [Update] Attach Stock info for Currency Display
    log_codes = [l.stock_code for l in investment_logs if l.stock_code]
    stock_map = {s.code: s for s in Stock.objects.filter(code__in=log_codes)}
    
    for log in investment_logs:
        log.stock_obj = stock_map.get(log.stock_code)

    # AJAX logic
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        section = request.GET.get('section')
        if section == 'portfolio':
             return render(request, 'partials/portfolio_section.html', {'portfolio': portfolio})
        else:
             return render(request, 'partials/log_section.html', {'investment_logs': investment_logs})

    # Handle Draft Creation (Manual)
    if request.method == 'POST' and request.POST.get('action') == 'create_draft':
        stock_name = request.POST.get('stock_name')
        qty = int(request.POST.get('quantity', 0))
        amt = int(request.POST.get('total_amount', 0))
        account_id = request.POST.get('account_id') # [New]
        
        # Simple Draft Creation logic
        # Assuming finding stock code logic is omitted or simplified
        stock_code = "UNKNOWN"
        stock_obj = Stock.objects.filter(name=stock_name).first()
        
        # [NEW] Find Agent managing this stock
        related_agent = get_agent_by_stock(stock_name, stock_code)
        
        # Fallback to chat agent if provided (though strict requirement says use stock agent)
        # Here we only have user context, so if None, it remains None (correct).
            
        # [New] Get Account Object
        account_obj = None
        account_info_str = "미래에셋증권 (예금주: 꼼망컴퍼니)" # Default
        
        if account_id:
            account_obj = Account.objects.filter(id=account_id).first()
            if account_obj:
                 # Requested Format: 증권사명/별명 (e.g., 미래에셋/내계좌)
                 nick = account_obj.nickname if account_obj.nickname else "별명없음"
                 account_info_str = f"{account_obj.financial_institution}/{nick}"

        # [NEW] Generate Standard Content (No attachment for CEO)
        formatted_content = format_approval_content(
            stock_name=stock_name,
            stock_code=stock_code,
            quantity=qty,
            price=int(amt/qty) if qty > 0 else 0,
            total_amount=amt,
            trade_type='buy', 
            reason="CEO 직접 지시",
            include_attachment=False,
            account_info=account_info_str # [New]
        )
            
        Approval.objects.create(
            organization=user.organization,
            drafter=user,
            agent=related_agent, # Assign Agent if found
            title=f"[CEO] {stock_name} 매수",
            content=formatted_content,
            report_type='buy',
            status='pending',
            temp_stock_name=stock_name,
            temp_stock_code=stock_code,
            temp_quantity=qty,
            temp_total_amount=amt,
            temp_account=account_obj # [New] Save Account
        )
        return redirect('investment_management')

    # Handle Approval Action (Quick)
    if request.method == 'POST' and request.POST.get('action') == 'approve':
        log_id = request.POST.get('log_id')
        return redirect('approval_detail', pk=log_id)

    return render(request, 'investment_management.html', {
        'agents': agents,
        'portfolio': portfolio,
        'drafts': drafts,
        'investment_logs': investment_logs,
        'summary': summary,
        'all_stocks': Stock.objects.all().order_by('display_order', 'name'),
        'accounts': Account.objects.filter(organization=user.organization),
        'active_main_menu': 'portfolio',
        'active_sub_menu': 'holdings',
        'notifications': TradeNotification.objects.filter(organization=user.organization).order_by('-created_at')[:5]
    })

@login_required
def financial_management(request):
    user = request.user
    agents = get_sidebar_agents(user)
    
    selected_date_str = request.GET.get('date')
    selected_date = None
    if selected_date_str:
        selected_date = parse_date(selected_date_str)

    latest_snapshot = None

    if selected_date:
        latest_snapshot = DailySnapshot.objects.filter(organization=user.organization, date=selected_date).first()
        # For historical dates, we might want just transactions for that day? 
        # But User request implies "Last Balance" correctness generally.
        transactions = Transaction.objects.filter(organization=user.organization, timestamp__date=selected_date).order_by('-timestamp')
    else:
        # Real-time calculation using FinancialService
        latest_snapshot = FinancialService.calculate_financials(user.organization)
        transactions = Transaction.objects.filter(organization=user.organization).order_by('-timestamp')

    # [Dynamic Balance Calculation]
    # To fix "Last Balance" issue without rewriting all DB history
    # Use Aggregate Sum of transactions strictly to ensure table consistency
    aggregated_balance = transactions.aggregate(Sum('amount'))['amount__sum'] or 0
    running_bal = aggregated_balance
    
    transactions_list = list(transactions)
    
    for tx in transactions_list:
        tx.dynamic_balance = running_bal
        # Prepare for next row (older): The balance BEFORE this tx was (End - Amount)
        # Wait. Balance After Tx = running_bal.
        # Balance Before Tx = running_bal - tx.amount
        # Next row (older) 's Balance After = Balance Before This Tx
        running_bal = running_bal - tx.amount

    # Pagination for Transactions
    paginator = Paginator(transactions_list, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'financial_management.html', {
        'agents': agents,
        'latest_snapshot': latest_snapshot,
        'transactions': page_obj,
        'selected_date': selected_date_str,
        'active_main_menu': 'portfolio',
        'active_sub_menu': 'finance'
    })

@login_required
def cash_operation(request):
    if request.method == 'POST':
        op_type = request.POST.get('op_type')
        amount = int(request.POST.get('amount', 0))
        description = request.POST.get('description', '')
        
        if op_type == 'deposit':
             TransactionService.deposit(request.user.organization, amount, description)
             messages.success(request, "입금 완료되었습니다.") # [New]
        elif op_type == 'withdraw':
             TransactionService.withdraw(request.user.organization, amount, description)
             messages.success(request, "출금 완료되었습니다.") # [New]
             
        # Update snapshot immediately logic can be added here if needed
        create_daily_snapshot(request.user.organization.id)
        
    return redirect('financial_management')

@login_required
def create_self_approval(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        stock_id = request.POST.get('stock')
        
        agent_to_assign = None
        temp_stock_name = None
        temp_stock_code = None

        if stock_id:
            try:
                stock_obj = Stock.objects.get(id=stock_id)
                temp_stock_name = stock_obj.name
                temp_stock_code = stock_obj.code
                
                # Find Agent
                agent_to_assign = get_agent_by_stock(temp_stock_name, temp_stock_code)
            except Stock.DoesNotExist:
                pass

        Approval.objects.create(
            organization=request.user.organization,
            drafter=request.user,
            agent=agent_to_assign,
            title=title,
            content=content,
            report_type='gen', # General Report
            status='pending',
            temp_stock_name=temp_stock_name,
            temp_stock_code=temp_stock_code,
            temp_date=timezone.now().date()
        )

        messages.success(request, "기안이 작성되었습니다.") # [New]
        return redirect('approval_list')
        
    stocks = Stock.objects.all().order_by('name')
    return render(request, 'create_approval.html', {
        'stocks': stocks,
        'active_main_menu': 'approval', # [Fix] Sidebar
        'active_sub_menu': 'request'
    })

@login_required
def approval_list(request):
    agents = get_sidebar_agents(request.user)
    
    # [NEW] Search & Filter
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '') # all, pending, approved, rejected
    active_sub = 'all'
    
    approvals = Approval.objects.filter(organization=request.user.organization)
    
    if status_filter:
        approvals = approvals.filter(status=status_filter)
        active_sub = status_filter
        
    if search_query:
        # Title or Content or Stock Name
        approvals = approvals.filter(
            Q(title__icontains=search_query) | 
            Q(content__icontains=search_query) |
            Q(temp_stock_name__icontains=search_query)
        )
        
    approvals = approvals.order_by('-updated_at') # Latest update first
    
    return render(request, 'approval_list.html', {
        'agents': agents, 
        'approvals': approvals,
        'active_main_menu': 'approval',
        'active_sub_menu': active_sub,
        'search_query': search_query
    })

@login_required
def approval_detail(request, pk):
    user = request.user
    agents = get_sidebar_agents(user)
    approval = get_object_or_404(Approval, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save':
            approval.title = request.POST.get('title')
            approval.content = request.POST.get('content')
            approval.title = request.POST.get('title')
            approval.content = request.POST.get('content')
            approval.save()
            messages.success(request, "저장되었습니다.") # [New]
            return redirect('approval_detail', pk=pk)
            
        if action == 'approve':
            # Determine Source & Date
            log_source = 'ceo' if approval.drafter else 'sms'
            
            log_date = timezone.now()
            if approval.temp_date:
                # Set to specific date + 09:00:00
                dt = datetime.combine(approval.temp_date, time(9, 0, 0))
                log_date = timezone.make_aware(dt)

            # Create Investment Log
            new_log = InvestmentLog.objects.create(
                user=approval.drafter if approval.drafter else None,
                agent=approval.agent if approval.agent else None,
                source=log_source,
                stock_name=approval.temp_stock_name,
                stock_code=approval.temp_stock_code,
                quantity=approval.temp_quantity,
                total_amount=approval.temp_total_amount,
                status='approved',
                approved_at=log_date,
                account=approval.temp_account # [New] Link Account
            )
            approval.investment_log = new_log
            
            # Find/Create Stock Logic
            stock = Stock.objects.filter(code=approval.temp_stock_code).first()
            if not stock and approval.temp_stock_name:
                stock = Stock.objects.filter(name=approval.temp_stock_name).first()
            
            price = 0
            if approval.temp_quantity > 0:
                price = approval.temp_total_amount / approval.temp_quantity

            if approval.report_type == 'buy':
                TransactionService.buy_stock(
                    organization=user.organization,
                    stock=stock,
                    quantity=approval.temp_quantity,
                    price=price,
                    description=f"승인된 매수: {approval.title}",
                    account=approval.temp_account,
                    timestamp=log_date, # [New] Use Approval Date
                    approval=approval # [New] Link for Cascade Delete
                )
            elif approval.report_type == 'sell':
                # Realized Profit Calculation
                profit = 0
                try:
                    buy_txs = Transaction.objects.filter(
                        organization=user.organization,
                        related_asset=stock,
                        transaction_type='BUY'
                    )
                    
                    total_buy_qty = sum(abs(t.quantity) for t in buy_txs)
                    total_buy_amt = sum(abs(t.amount) - t.fee for t in buy_txs) # Deduct fees
                    
                    avg_buy_price = total_buy_amt / total_buy_qty if total_buy_qty > 0 else 0
                    profit = (price - float(avg_buy_price)) * approval.temp_quantity
                except Exception:
                    profit = 0
                
                TransactionService.sell_stock(
                    organization=user.organization,
                    stock=stock,
                    quantity=approval.temp_quantity,
                    price=price,
                    profit=profit,
                    description=f"승인된 매도: {approval.title}",
                    approval=approval # [New] Link
                )
            
            create_daily_snapshot(request.user.organization.id)
            approval.status = 'approved'
            approval.save()
            messages.success(request, "승인 완료되었습니다.") # [New]
            return redirect('approval_list')
            
        elif action == 'reject':
            approval.status = 'rejected'
            approval.save()
            messages.success(request, "반려되었습니다.") # [New]
            return redirect('approval_list')

    return render(request, 'approval_detail.html', {
        'agents': agents, 
        'approval': approval,
        'active_main_menu': 'approval' # [Fix] Maintain Sidebar
    })

@login_required
def org_chart(request):
    user = request.user
    agents = get_sidebar_agents(user)
    org = user.organization

    if not org:
        return render(request, 'org_chart.html', {'agents': agents, 'chart_data': json.dumps([])})

    # 1. Start building chart data
    rows = []

    # 2. Add CEO (Root)
    ceo = User.objects.filter(organization=org, role='ceo').first()
    ceo_id = f"USER_{ceo.id}" if ceo else f"CEO_{org.id}"
    ceo_name = ceo.username if ceo else "CEO"
    ceo_pos = ceo.position if ceo and ceo.position else "대표이사"
    
    # [v: ID, f: Display HTML]
    rows.append([
        {'v': ceo_id, 'f': f'<div class="node-card ceo-card"><div class="profile-icon">👑</div><div class="node-name">{ceo_name}</div><div class="node-role">{ceo_pos}</div></div>'},
        '', # No parent
        'CEO'
    ])

    # 3. Add Departments
    departments = Department.objects.filter(organization=org)
    for dept in departments:
        dept_id = f"DEPT_{dept.id}"
        parent_id = f"DEPT_{dept.parent.id}" if dept.parent else ceo_id
        
        rows.append([
            {'v': dept_id, 'f': f'<div class="node-card dept-card"><div class="node-name">{dept.name}</div></div>'},
            parent_id,
            dept.name
        ])

    # 4. Add Agents
    all_agents = Agent.objects.filter(organization=org).select_related('department_obj').prefetch_related('managed_stocks')
    for agent in all_agents:
        agent_id = f"AGENT_{agent.id}"
        parent_id = f"DEPT_{agent.department_obj.id}" if agent.department_obj else ceo_id
        
        img_url = agent.profile_image.url if agent.profile_image else ""
        img_html = f'<img src="{img_url}" style="width:100%; height:100%; object-fit:cover;">' if img_url else '👤'
        
        # Managed Stocks Display
        stocks = agent.managed_stocks.all()
        stock_list_str = ""
        if stocks:
            names = [s.name for s in stocks]
            display_list = []
            for i, name in enumerate(names, 1):
                display_list.append(f"{i}. {name}")
            
            list_style = "text-align:left; font-size:11px; margin-top:8px; color:#475569; line-height:1.4;"
            
            visible_html = "<br>".join(display_list)
            stock_list_str = f"<div class='node-stock' style='{list_style}'>{visible_html}</div>"

        # Admin Link
        admin_link = f"<a href='/admin/core/agent/{agent.id}/change/' target='_blank' style='text-decoration:none; position:absolute; top:5px; right:5px; font-size:12px;'>⚙️</a>"

        # HTML Construction
        # Line 1: Name + Position (Large & Bold)
        # Line 2: Role (Small & Gray)
        rows.append([
            {'v': agent_id, 'f': f'''<div class="node-card agent-card" style="position:relative;">
                {admin_link}
                <div class="img-circle">{img_html}</div>
                <div class="node-name">{agent.name} {agent.position}</div>
                <div class="node-role" style="font-size:11px; font-weight:normal; color:#64748b; margin-top:-2px;">{agent.role}</div>
                {stock_list_str}
            </div>'''},
            parent_id,
            agent.role
        ])

    # Prepare raw data for D3.js
    departments = Department.objects.filter(organization=org)
    all_agents = Agent.objects.filter(organization=org).select_related('department_obj')
    ceo = User.objects.filter(organization=org, role='ceo').first()

    return render(request, 'org_chart.html', {
        'agents': agents, # For Sidebar
        'departments': departments,
        'all_agents': all_agents,
        'ceo': ceo,
        'active_main_menu': 'approval' if request.GET.get('action') == 'request' else 'home',
        'active_sub_menu': 'request' if request.GET.get('action') == 'request' else 'org'
    })

@method_decorator(csrf_exempt, name='dispatch')
class SmsWebhookView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            secret_key = data.get('secret_key')
            content = data.get('content') or data.get('sms_content')
            
            # Simple UserProfile check
            from .models import UserProfile
            profile = UserProfile.objects.filter(secret_key=secret_key).first()
            if not profile: return HttpResponse("Unauthorized", status=401)
            
            parsed = parse_mirae_sms(content)
            
            # [NEW] Save Raw Notification
            notification = TradeNotification.objects.create(
                organization=profile.user.organization,
                content=content
            )

            if parsed and parsed['trade_type']:
                # Update Notification with parsed data
                notification.stock_name = parsed['stock_name']
                notification.stock_code = parsed['stock_code']
                notification.trade_type = parsed['trade_type']
                notification.quantity = parsed['quantity']
                notification.price = parsed['price']
                notification.amount = parsed['amount']
                notification.is_parsed = True
                notification.save()

                user = profile.user
                action_label = "매수" if parsed['trade_type'] == 'buy' else "매도"
                stock_name = parsed['stock_name'] or parsed['stock_code']
                
                # Create Manual-like Draft for Approval
                encoded_title = f"[SMS] {stock_name} {action_label}"
                
                # [NEW] Find Agent
                # [NEW] Find Agent using Utility
                # We have parsed stock_name and stock_code
                related_agent = get_agent_by_stock(stock_name, parsed.get('stock_code'))

                # [NEW] Standard Content (With attachment for SMS)
                formatted_content = format_approval_content(
                    stock_name=stock_name,
                    stock_code=parsed['stock_code'] or "Unknown",
                    quantity=parsed['quantity'],
                    price=parsed['price'],
                    total_amount=parsed['amount'],
                    trade_type=parsed['trade_type'],
                    reason="SMS 체결 알림",
                    include_attachment=True
                )

                Approval.objects.create(
                    organization=user.organization,
                    drafter=None, # SMS source trigger
                    agent=related_agent, # Assign Agent
                    title=encoded_title,
                    content=formatted_content,
                    report_type=parsed['trade_type'],
                    status='pending',
                    temp_stock_name=stock_name,
                    temp_stock_code=parsed['stock_code'],
                    temp_quantity=parsed['quantity'],
                    temp_total_amount=parsed['amount'],
                    temp_date=timezone.now().date()
                )
             
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# [NEW] Stock Management Views
@login_required
def stock_management(request):
    user = request.user
    agents = get_sidebar_agents(user)
    
    # [UPDATE] Tri-state Sorting Logic
    # sort param: 'name', 'country', 'price', or empty (default)
    # direction: 'asc', 'desc'
    
    sort_by = request.GET.get('sort', '')
    direction = request.GET.get('direction', 'asc')
    
    stocks = Stock.objects.all()
    
    # Apply Sort
    if sort_by == 'name':
        if direction == 'desc':
            stocks = stocks.order_by('-name')
        else:
            stocks = stocks.order_by('name')
            
    elif sort_by == 'country':
        if direction == 'desc':
            stocks = stocks.order_by('-country', 'name')
        else:
            stocks = stocks.order_by('country', 'name')
            
    elif sort_by == 'price':
        if direction == 'asc': # Reverse default for price usually (High to Low is better default, but sticking to logic)
            stocks = stocks.order_by('current_price')
        else:
            stocks = stocks.order_by('-current_price')
            
    else:
        # Default: Manual Order
        stocks = stocks.order_by('display_order', 'name')

    # [NEW] Determine which stocks are in portfolio (quantity > 0)
    # Using Transaction aggregation
    held_qty_map = {}
    try:
        holdings = Transaction.objects.filter(
            organization=user.organization,
            related_asset__isnull=False
        ).values('related_asset').annotate(total_qty=Sum('quantity')).filter(total_qty__gt=0)
        
        for h in holdings:
            held_qty_map[h['related_asset']] = h['total_qty']
    except Exception:
        pass
        
    # Annotate list
    stocks_list = list(stocks)
    for s in stocks_list:
        qty = held_qty_map.get(s.id, 0)
        price = s.current_price if s.current_price else 0
        # User requested: holding amount >= 1 won
        s.is_held = (qty * price) >= 1
        
    stocks = stocks_list # Swap query set with annotated list


    return render(request, 'stock_management.html', {
        'agents': agents,
        'stocks': stocks,
        'current_sort': sort_by,
        'current_direction': direction,
        'active_main_menu': 'portfolio',
        'active_sub_menu': 'stocks'
    })

@login_required
@csrf_exempt
def delete_approval(request, pk):
    """
    기안문 삭제 (안전장치 포함)
    기안문 삭제 시 연결된 Transaction도 Cascade로 삭제됨.
    """
    if request.method != 'POST':
        return HttpResponse("POST method required", status=405)
        
    approval = get_object_or_404(Approval, pk=pk)
    
    # Permission Check
    if not (request.user == approval.drafter or request.user.is_superuser):
        return HttpResponse("권한이 없습니다.", status=403)
        
    try:
        with transaction.atomic():
            # Cascade Delete
            # approval.delete() will delete related Transaction, ApprovalLine, InvestmentLog (if OneToOne is Cascade? Wait)
            # InvestmentLog is OneToOne but specific deletion might be safer to be explicit or check model `on_delete`.
            # Check model: investment_log = OneToOneField(..., on_delete=SET_NULL) -> in Approval.
            # So deleting Approval sets InvLog to Null.
            # BUT User said: "Delete ALL related transaction history".
            
            # 1. Delete Linked Transaction (Handled by FK on Transaction I just added with CASCADE)
            
            # 2. Delete Investment Log (if exists)
            if approval.investment_log:
                approval.investment_log.delete()
                
            # 3. Delete Approval
            approval.delete()
            
            # Recalculate Snapshot immediately to reflect changes
            create_daily_snapshot(request.user.organization.id)

            messages.success(request, "기안문이 삭제되었습니다.") # [New]
            
        return redirect('approval_list')
        
    except Exception as e:
        return HttpResponse(f"삭제 중 오류 발생: {str(e)}", status=500)

@login_required
@csrf_exempt
def delete_chat_room(request, pk):
    """
    채팅방(일반기안) 목록에서 즉시 삭제
    """
    if request.method != 'POST':
        return HttpResponse("POST method required", status=405)
        
    approval = get_object_or_404(Approval, pk=pk)
    
    # Permission Check
    if not (request.user == approval.drafter or request.user.is_superuser):
        return HttpResponse("권한이 없습니다.", status=403)
    
    try:
        approval.delete()
        create_daily_snapshot(request.user.organization.id)
        messages.success(request, "채팅방에서 나갔습니다.") # [New]
        return redirect('approval_list')
    except Exception as e:
        return HttpResponse(f"삭제 중 오류 발생: {str(e)}", status=500)

@login_required
@csrf_exempt
def update_stock_ordering(request):
    """
    AJAX API to update stock display order
    Supports both JSON body and Form Data (HTMX)
    """
    if request.method == 'POST':
        try:
            order_list = []
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                order_list = data.get('order', [])
            else:
                order_list = request.POST.getlist('order')

            if not order_list:
                return JsonResponse({'status': 'error', 'message': 'Empty order list'}, status=400)
                
            # Update display_order logic...
            
            # Bulk update can be tricky with different values, 
            # so we use a transaction or simple loop (since list is small < 50 usually)
            for index, stock_id in enumerate(order_list):
                 Stock.objects.filter(id=stock_id).update(display_order=index)
                 
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

@login_required
def add_interest_stock(request):
    if request.method == 'POST':
        keyword = request.POST.get('keyword')
        if not keyword:
            return redirect('stock_management')
        
        try:
            # 1. DB Search
            stock = Stock.objects.filter(Q(name__icontains=keyword) | Q(code=keyword)).first()
            
            # 2. External Search (Yahoo Finance API)
            if not stock:
                search_code = keyword
                
                # A. If keyword is NOT a 6-digit code, try to find the ticker via Search API
                if not (keyword.isdigit() and len(keyword) == 6):
                    try:
                        import requests
                        url = "https://query2.finance.yahoo.com/v1/finance/search"
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        params = {'q': keyword, 'quotesCount': 5, 'newsCount': 0}
                        
                        response = requests.get(url, headers=headers, params=params, timeout=5)
                        data = response.json()
                        
                        if 'quotes' in data and len(data['quotes']) > 0:
                            # Prioritize Korean stocks (.KS, .KQ)
                            found_ticker = None
                            for q in data['quotes']:
                                symbol = q.get('symbol', '')
                                if symbol.endswith('.KS') or symbol.endswith('.KQ'):
                                    found_ticker = symbol
                                    break
                            
                            # If no Korean stock found, take the first one (e.g., US stock)
                            if not found_ticker:
                                found_ticker = data['quotes'][0]['symbol']
                                
                            search_code = found_ticker
                    except Exception as e:
                        print(f"Search API failed: {e}")
                        # Fallback to original keyword
                        pass

                # B. Try creating from yfinance with the resolved code
                if search_code.isdigit() and len(search_code) == 6:
                     search_code = f"{search_code}.KS"
                
                ticker = yf.Ticker(search_code)
                info = ticker.fast_info
                current_price = info.last_price
                
                if current_price:
                    full_info = ticker.info
                    stock_name = keyword
                    try: 
                        stock_name = full_info.get('longName', full_info.get('shortName', keyword))
                    except: 
                        pass
                    
                    # Clean code
                    db_code = search_code
                    if search_code.endswith('.KS'):
                        check_code = search_code.replace('.KS', '')
                        if check_code.isdigit() and len(check_code) == 6:
                            db_code = check_code
                    
                    # [UPDATE] Try Naver for Metal Data
                    market_cap = None
                    description = ""
                    if db_code.isdigit() and len(db_code) == 6:
                        naver_name = get_naver_stock_name(db_code)
                        if naver_name:
                            stock_name = naver_name
                        
                        naver_data = get_naver_stock_extra_info(db_code, full_info.get('exchange', ''))
                        market_cap = naver_data.get('market_cap')
                        description = naver_data.get('description', '')
                    else:
                        # World Stock
                        naver_data = get_naver_stock_extra_info(db_code, full_info.get('exchange', ''))
                        if naver_data.get('description'):
                            description = naver_data['description']

                    country_ko = identify_stock_country(search_code, full_info)

                    stock, created = Stock.objects.get_or_create(
                        code=db_code,
                        defaults={
                            'name': stock_name,
                            'current_price': current_price,
                            'country': country_ko,
                            'market_cap': market_cap,
                            'description': description
                        }
                    )
                    # Update if exists but name/price might be old? (Optional, skipping for now)

            # [Removed] InterestStock creation -> Now purely Stock creation
                
        except Exception as e:
            print(f"Error adding interest stock: {e}")
            pass
            
    return redirect('stock_management')

@login_required
def delete_interest_stock(request, stock_id):
    """
    Remove stock from system (Admin Sync)
    """
    if request.method == 'POST':
        try:
            # [UPDATE] Delete Stock Object entirely
            Stock.objects.get(id=stock_id).delete()
        except Exception as e:
            print(f"Error deleting stock: {e}")
            pass
            
    return redirect('stock_management')

# [Old get_stock_detail removed]

def get_stock_detail(request):
    """
    Ajax로 종목 상세 정보 반환 (API)
    Refactored to use centralized update_stock utils function.
    """
    stock_id = request.GET.get('stock_id')
    try:
        stock = Stock.objects.get(id=stock_id)
        
        # Trigger centralized update (Optimized: 1mo inc)
        from .utils import update_stock
        success = update_stock(stock)
        
        if not success:
            print(f"Update failed for {stock.name}, serving cached data.")
        
        # Refresh from DB after update
        stock.refresh_from_db()
        
        # Ensure candle_data is list
        candles = stock.candle_data if isinstance(stock.candle_data, list) else []
        
        return JsonResponse({
            'success': True,
            'name': stock.name,
            'code': stock.code,
            'price': stock.current_price,
            'market_cap': stock.market_cap,
            'per': stock.per,
            'pbr': stock.pbr,
            'high_52w': stock.high_52w,
            'low_52w': stock.low_52w,
            'description': stock.description,
            'candles': candles
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def search_stock_api(request):
    """
    Yahoo Finance Auto-complete Proxy
    GET /stock/search/?q=...
    """
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'quotes': []})
    
    try:
        import requests
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        params = {
            'q': query,
            'quotesCount': 10,
            'newsCount': 0
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        data = response.json()
        
        if 'quotes' not in data:
            return JsonResponse({'quotes': []})
            
        results = []
        # Filter and format results
        for q in data['quotes']:
            symbol = q.get('symbol', '')
            shortname = q.get('shortname', '')
            longname = q.get('longname', shortname)
            exch = q.get('exchange', '')
            
            # Label for UI
            label = f"{longname} ({symbol})"
            
            results.append({
                'symbol': symbol,
                'name': longname,
                'exch': exch,
                'label': label
            })
            
        return JsonResponse({'quotes': results})
        
    except Exception as e:
        return JsonResponse({'error': str(e), 'quotes': []})


@login_required
def account_management(request):
    # Trigger Server Restart
    user = request.user
    agents = get_sidebar_agents(user)
    accounts = Account.objects.filter(organization=user.organization).order_by('-is_default', 'created_at')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            Account.objects.create(
                organization=user.organization,
                financial_institution=request.POST.get('financial_institution'),
                account_number=request.POST.get('account_number'),
                account_holder=request.POST.get('account_holder'),
                nickname=request.POST.get('nickname')
            )
        elif action == 'edit':
            acc_id = request.POST.get('account_id')
            acc = get_object_or_404(Account, id=acc_id, organization=user.organization)
            acc.financial_institution = request.POST.get('financial_institution')
            acc.account_number = request.POST.get('account_number')
            acc.account_holder = request.POST.get('account_holder')
            acc.nickname = request.POST.get('nickname')
            acc.save()
        elif action == 'delete':
            acc_id = request.POST.get('account_id')
            acc = get_object_or_404(Account, id=acc_id, organization=user.organization)
            if not acc.is_default: # Prevent deleting default account
                # Check for related transactions
                if Transaction.objects.filter(account=acc).exists():
                    messages.error(request, "거래 내역이 존재하는 계좌는 삭제할 수 없습니다.")
                else:
                    acc.delete()
                    messages.success(request, "계좌가 삭제되었습니다.")
            else:
                messages.error(request, "기본 계좌는 삭제할 수 없습니다.")
        
        return redirect('account_management')

    # AJAX for Portfolio
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        action = request.GET.get('action')
        if action == 'get_portfolio':
            account_id = request.GET.get('account_id')
            account = get_object_or_404(Account, id=account_id, organization=user.organization)
            portfolio = FinancialService.get_portfolio_data(user.organization, account=account)
            return render(request, 'partials/account_portfolio.html', {'portfolio': portfolio})

    return render(request, 'account_management.html', {
        'agents': agents, 
        'accounts': accounts,
        'active_main_menu': 'portfolio',
        'active_sub_menu': 'account'
    })

@login_required
def trade_notification_list(request):
    """
    체결 알림(SMS) 리스트 조회
    필터: 시간순, 종목명순, 금액순
    """
    user = request.user
    agents = get_sidebar_agents(user)
    
    sort_by = request.GET.get('sort', 'created_at')
    direction = request.GET.get('direction', 'desc')
    
    # Base Query
    notifications = TradeNotification.objects.filter(organization=user.organization)
    
    # Sorting
    ordering = []
    prefix = '-' if direction == 'desc' else ''
    
    if sort_by == 'time' or sort_by == 'created_at':
        ordering.append(f'{prefix}created_at')
    elif sort_by == 'stock':
        ordering.append(f'{prefix}stock_name')
    elif sort_by == 'amount':
        ordering.append(f'{prefix}amount')
    else:
        ordering.append('-created_at') # Default
        
    notifications = notifications.order_by(*ordering)
    
    return render(request, 'trade_notification_list.html', {
        'agents': agents,
        'notifications': notifications,
        'current_sort': sort_by,
        'current_direction': direction,
        'active_main_menu': 'portfolio',
        'active_sub_menu': 'noti'
    })

@login_required
def update_all_stocks_api(request):
    """
    API to trigger update for all stocks or a specific stock.
    POST /api/stock/update/
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)
        
    try:
        from . import utils
        import json
        
        # Check if specific stock requested
        data = json.loads(request.body) if request.body else {}
        stock_id = data.get('stock_id')
        
        if stock_id:
            stock = Stock.objects.get(id=stock_id)
            if utils.update_stock(stock):
                messages.success(request, f'{stock.name} 업데이트 완료.') # [New]
                return JsonResponse({'status': 'success', 'message': f'{stock.name} updated.'})
            else:
                return JsonResponse({'status': 'error', 'message': f'Failed to update {stock.name}.'})
        else:
            # Update all
            stocks = Stock.objects.all()
            count = 0
            for stock in stocks:
                if utils.update_stock(stock):
                    count += 1
            
            messages.success(request, f'전체 {count}개 종목 평가금액 업데이트 완료.') # [New]
            return JsonResponse({'status': 'success', 'message': f'{count} stocks updated.'})
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ==========================================
# [New] My Info (User & Organization & Disclosure)
# ==========================================
@login_required
def my_info(request):
    user = request.user
    organization = user.organization

    if request.method == 'POST':
        # 1. Update User/Org Info
        if 'update_info' in request.POST:
            user_form = UserChangeForm(request.POST, instance=user)
            org_form = OrganizationForm(request.POST, request.FILES, instance=organization)
            
            if user_form.is_valid() and org_form.is_valid():
                user_form.save()
                org_form.save()
                messages.success(request, "정보가 수정되었습니다.")
                return redirect('my_info')
        
        # 2. Update Password
        elif 'update_password' in request.POST:
            return redirect('admin:password_change')

        # 3. Update Portfolio Disclosure
        elif 'update_disclosure' in request.POST:
            public_stock_ids = request.POST.getlist('public_stocks')
            my_interest_stocks = InterestStock.objects.filter(user=user)
            
            for interest in my_interest_stocks:
                stock = interest.stock
                is_public = str(stock.id) in public_stock_ids
                PortfolioDisclosure.objects.update_or_create(
                    user=user, 
                    stock=stock, 
                    defaults={'is_public': is_public}
                )
            messages.success(request, "포트폴리오 공개 설정이 저장되었습니다.")
            return redirect('my_info')

    # Init Forms
    user_form = UserChangeForm(instance=user)
    org_form = OrganizationForm(instance=organization)

    # Prepare Stock List
    my_stocks = InterestStock.objects.filter(user=user).select_related('stock')
    
    stock_disclosure_list = []
    for item in my_stocks:
        disclosure = PortfolioDisclosure.objects.filter(user=user, stock=item.stock).first()
        is_public = disclosure.is_public if disclosure else True
        stock_disclosure_list.append({
            'stock': item.stock,
            'is_public': is_public
        })

    # [New] Social Stats
    followers_count = Follow.objects.filter(following=user).count()
    following_count = Follow.objects.filter(follower=user).count()
    following_list = Follow.objects.filter(follower=user).select_related('following')

    return render(request, 'my_info.html', {
        'user': user,
        'user_form': user_form,
        'org_form': org_form,
        'stock_disclosures': stock_disclosure_list,
        'followers_count': followers_count,
        'following_count': following_count,
        'following_list': following_list, # For management modal
        'active_main_menu': 'my_info',
    })

# ==========================================
# [New] Community (Board)
# ==========================================
@login_required
def post_list(request):
    category = request.GET.get('category', 'all')
    search_query = request.GET.get('q', '')
    
    posts = Post.objects.all().select_related('author', 'organization').order_by('-created_at')
    
    if category != 'all':
        posts = posts.filter(category=category)
        
    if search_query:
        posts = posts.filter(Q(title__icontains=search_query) | Q(content__icontains=search_query))

    paginator = Paginator(posts, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'community/post_list.html', {
        'page_obj': page_obj,
        'category': category,
        'search_query': search_query,
        'active_main_menu': 'community',
    })

@login_required
def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)
    
    # Increment View Count
    # Use F() expression to avoid race conditions
    Post.objects.filter(pk=pk).update(views=F('views') + 1)
    post.refresh_from_db()
    
    # Check if I follow the author
    is_following = False
    if request.user.is_authenticated and request.user != post.author:
        is_following = Follow.objects.filter(follower=request.user, following=post.author).exists()
        
    return render(request, 'community/post_detail.html', {
        'post': post,
        'is_following': is_following,
        'active_main_menu': 'community',
    })

@login_required
def post_create(request):
    if request.method == 'POST':
        category = request.POST.get('category')
        title = request.POST.get('title')
        content = request.POST.get('content')
        
        if category and title and content:
            Post.objects.create(
                author=request.user,
                organization=request.user.organization,
                category=category,
                title=title,
                content=content
            )
            messages.success(request, "게시글이 등록되었습니다.")
            return redirect('post_list')
        else:
            messages.error(request, "모든 필드를 입력해주세요.")
            
    return render(request, 'community/post_form.html', {
        'title': '새 게시글 작성',
        'active_main_menu': 'community',
    })

@login_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    
    # Permission Check
    if post.author != request.user:
        messages.error(request, "수정 권한이 없습니다.")
        return redirect('post_detail', pk=pk)
        
    if request.method == 'POST':
        category = request.POST.get('category')
        title = request.POST.get('title')
        content = request.POST.get('content')
        
        post.category = category
        post.title = title
        post.content = content
        post.save()
        
        messages.success(request, "게시글이 수정되었습니다.")
        return redirect('post_detail', pk=pk)
        
    return render(request, 'community/post_form.html', {
        'title': '게시글 수정',
        'post': post,
        'active_main_menu': 'community',
    })

@login_required
def post_delete(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if post.author == request.user or request.user.is_superuser:
        post.delete()
        messages.success(request, "게시글이 삭제되었습니다.")
    else:
        messages.error(request, "삭제 권한이 없습니다.")
        
    return redirect('post_list')


# ==========================================
# [New] Portfolio Ranking (SaaS)
# ==========================================
@login_required
def portfolio_ranking(request):
    user = request.user
    
    # 1. Access Check: Must have at least 1 public stock
    my_public_count = PortfolioDisclosure.objects.filter(user=user, is_public=True).count()
    if my_public_count == 0:
        messages.warning(request, "랭킹을 보려면 내 포트폴리오를 최소 1개 이상 공개해야 합니다.")
        return redirect('my_info')
        
    # 2. Calculate Ranking Data
    # Target: Users who have at least 1 public stock
    # Logic:
    # - Iterate candidates
    # - Calculate Total Asset (from InvestmentLog or InterestStock 'amount' * current price?)
    #   * Note: InvestmentLog is historical. InterestStock is current holdings but doesn't track bought price well for yield.
    #   * Better: Use `InvestmentLog` aggregation for Total Buy/Sell -> Realized PnL? 
    #   * OR: Just sum up `account.balance` + `stock value`.
    #   * For simplicity & MVP: 
    #     - Total Asset = Organization.cash_balance + Sum(InterestStock.amount * Stock.current_price)
    #     - Total Yield = (Total Asset - Initial Capital) / Initial Capital * 100? (Hard to track initial)
    #     - Alternative Yield: Sum(InterestStock PnL) / Sum(Buy Cost)
    
    # [Refined Logic utilizing InvestmentLog for accuracy]
    candidates = User.objects.filter(role='ceo').select_related('organization')
    ranking_data = []
    
    for candidate in candidates:
        # 1. Check Participation
        public_disclosures = PortfolioDisclosure.objects.filter(user=candidate, is_public=True).select_related('stock')
        if not public_disclosures.exists():
            continue
            
        public_stock_ids = [pd.stock.id for pd in public_disclosures]
        
        # 2. Calculate Portfolio Stats from InvestmentLog (Actual Ledger)
        logs = InvestmentLog.objects.filter(user=candidate, action__in=['buy', 'sell']).select_related('stock')
        
        # Group by stock to calculate weighted average yield
        stock_stats = {} # { stock_id: { 'total_qty': 0, 'total_cost': 0, 'current_value': 0 } }
        
        total_investment_cost = 0
        current_total_value = 0
        
        # Simplified calculation: 
        # For each log, if buy -> add cost/qty. if sell -> remove cost/qty (FIFO or Avg).
        # Since it's complex, let's use a simpler current-state snapshot approch if possible.
        # Check if `InterestStock` has the current holding amount?
        # If not, let's assume `InvestmentLog` is the source of truth.
        
        # [Alternative] Use simple aggregation for MVP
        # Total Asset = Org Cash + Stock Valuation
        org_cash = candidate.organization.cash_balance
        
        # Calculate Stock Valuation
        # We need per-stock quantity. 
        # Let's retrieve this from `InterestStock` assuming it syncs with holdings (as per my_info logic).
        interest_stocks = InterestStock.objects.filter(user=candidate).select_related('stock')
        
        stock_valuation = 0
        public_stock_valuation = 0
        public_stock_profit = 0
        public_stock_cost = 0
        
        # Note: InterestStock usually needs to store 'quantity' and 'average_price' to be useful here.
        # If it doesn't, we must rely on logs.
        # Let's try to infer from logs quickly.
        
        portfolio_map = {}
        for log in logs:
            sid = log.stock.id
            if sid not in portfolio_map:
                portfolio_map[sid] = {'qty': 0, 'cost': 0}
            
            if log.action == 'buy':
                portfolio_map[sid]['qty'] += log.amount
                portfolio_map[sid]['cost'] += (log.amount * log.price)
            elif log.action == 'sell':
                # Reduce cost proportionally
                if portfolio_map[sid]['qty'] > 0:
                    avg_price = portfolio_map[sid]['cost'] / portfolio_map[sid]['qty']
                    portfolio_map[sid]['cost'] -= (log.amount * avg_price)
                    portfolio_map[sid]['qty'] -= log.amount

        # Value Calculation
        for sid, data in portfolio_map.items():
            qty = data['qty']
            cost = data['cost']
            
            if qty > 0:
                try:
                    current_price = Stock.objects.get(id=sid).current_price
                    val = qty * current_price
                    
                    stock_valuation += val
                    total_investment_cost += cost
                    
                    # If this stock is public
                    if sid in public_stock_ids:
                        public_stock_valuation += val
                        public_stock_cost += cost
                except:
                    pass

        total_asset = org_cash + stock_valuation
        
        # Calculate Yields
        total_yield = 0
        if total_investment_cost > 0:
            total_yield = ((stock_valuation - total_investment_cost) / total_investment_cost) * 100
            
        public_yield = 0
        if public_stock_cost > 0:
            public_yield = ((public_stock_valuation - public_stock_cost) / public_stock_cost) * 100

        ranking_data.append({
            'user': candidate,
            'organization': candidate.organization,
            'total_asset': total_asset,
            'total_yield': round(total_yield, 2),
            'public_yield': round(public_yield, 2),
            'stock_count': len(public_stock_ids)
        })

    # Sort
    sort_by = request.GET.get('sort', 'asset')
    if sort_by == 'asset':
        ranking_data.sort(key=lambda x: x['total_asset'], reverse=True)
    elif sort_by == 'yield':
        ranking_data.sort(key=lambda x: x['total_yield'], reverse=True)
    elif sort_by == 'public':
        ranking_data.sort(key=lambda x: x['public_yield'], reverse=True)
    
    # Add Rank
    for idx, item in enumerate(ranking_data):
        item['rank'] = idx + 1
        
    return render(request, 'community/portfolio_ranking.html', {
        'ranking_data': ranking_data,
        'active_main_menu': 'community', 
        'sort_by': sort_by
    })


# ==========================================
# [New] Social Feed (Instagram Style)
# ==========================================
@login_required
def feed(request):
    user = request.user
    
    # 1. Get List of Following
    following_ids = Follow.objects.filter(follower=user).values_list('following_id', flat=True)
    
    # 2. Feed Algorithm
    # - Following Posts: High priority
    # - Popular Posts: Low priority (Discovery)
    # - Mix: Latest posts from following + Inject popular posts every N items?
    # Simple approach: Union or just two separate lists, or fetch sorted by date from combined query.
    
    # Fetch Following Posts
    following_posts = Post.objects.filter(author_id__in=following_ids).select_related('author', 'organization')
    
    # Fetch Popular Posts (High Views, excluding Following)
    popular_posts = Post.objects.exclude(author_id__in=following_ids).exclude(author=user).filter(views__gte=10).order_by('-views', '-created_at')[:5]
    
    # Merge and Sort (in Python) to interleave? 
    # Or just show "Following" feed primarily, and a "Recommended" section.
    # User Request: "중간중간에 인기글도 피드에 삽입해".
    
    # Strategy: Fetch top 50 posts from following.
    feed_items = list(following_posts.order_by('-created_at')[:50])
    pop_items = list(popular_posts)
    
    # Interleave: Every 3 posts, insert 1 popular post
    final_feed = []
    pop_idx = 0
    
    if not feed_items and pop_items:
        # If no following, just show popular
        final_feed = pop_items
    else:
        for i, post in enumerate(feed_items):
            final_feed.append({'type': 'following', 'post': post})
            if (i + 1) % 3 == 0 and pop_idx < len(pop_items):
                final_feed.append({'type': 'popular', 'post': pop_items[pop_idx]})
                pop_idx += 1
                
        # Append remaining popular if feed is short
        while pop_idx < len(pop_items):
            final_feed.append({'type': 'popular', 'post': pop_items[pop_idx]})
            pop_idx += 1

    return render(request, 'community/feed.html', {
        'feed_items': final_feed,
        'active_main_menu': 'community',
        'active_sub_menu': 'feed'
    })

@login_required
def follow_toggle(request, user_id):
    if request.method == 'POST':
        target_user = get_object_or_404(User, pk=user_id)
        
        if target_user == request.user:
            messages.error(request, "자신을 팔로우할 수 없습니다.")
            return redirect(request.META.get('HTTP_REFERER', 'feed'))
            
        follow, created = Follow.objects.get_or_create(follower=request.user, following=target_user)
        
        if not created:
            # Already exists -> Unfollow
            follow.delete()
            # messages.info(request, f"{target_user.username} 님을 언팔로우했습니다.")
        else:
            pass
            # messages.success(request, f"{target_user.username} 님을 팔로우했습니다.")
            
        return redirect(request.META.get('HTTP_REFERER', 'feed'))
    return redirect('feed')



