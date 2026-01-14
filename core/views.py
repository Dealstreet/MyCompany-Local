import datetime
import re
import json
import yfinance as yf
from itertools import groupby
from operator import attrgetter
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from datetime import datetime, time
from django.http import JsonResponse, HttpResponse

from .models import User, Organization, Department, DailySnapshot, Transaction, Stock, InterestStock, Agent, Message, Approval, InvestmentLog, Account, TradeNotification
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
    return render(request, 'index.html', {'agents': agents})

@login_required
def messenger(request, agent_id=None):
    user = request.user
    agents = get_sidebar_agents(user)
    
    if not agent_id and agents.exists():
        return redirect('messenger', agent_id=agents.first().id)
        
    active_agent = get_object_or_404(Agent, id=agent_id) if agent_id else None
    
    messages = []
    if active_agent:
        messages = Message.objects.filter(
            agent=active_agent, 
            user=user
        ).order_by('created_at')

    initial_greeting = "안녕하세요."
    if active_agent:
        hour = datetime.datetime.now().hour
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
        'messages': messages,
        'initial_greeting': initial_greeting
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
        
        # Simple Draft Creation logic
        # Assuming finding stock code logic is omitted or simplified
        stock_code = "UNKNOWN"
        stock_obj = Stock.objects.filter(name=stock_name).first()
        
        # [NEW] Find Agent managing this stock
        related_agent = get_agent_by_stock(stock_name, stock_code)
        
        # Fallback to chat agent if provided (though strict requirement says use stock agent)
        # Here we only have user context, so if None, it remains None (correct).
            
        # [NEW] Generate Standard Content (No attachment for CEO)
        formatted_content = format_approval_content(
            stock_name=stock_name,
            stock_code=stock_code,
            quantity=qty,
            price=int(amt/qty) if qty > 0 else 0,
            total_amount=amt,
            trade_type='buy', # Manual draft usually buy, or add toggle? User said "CEO Order" usually implies buy in this context or needs selector. Existing code hardcoded 'buy'.
            reason="CEO 직접 지시",
            include_attachment=False
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
            temp_total_amount=amt
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
        'accounts': Account.objects.filter(organization=user.organization)
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
    transactions = Transaction.objects.filter(organization=user.organization).order_by('-timestamp')

    if selected_date:
        latest_snapshot = DailySnapshot.objects.filter(organization=user.organization, date=selected_date).first()
    else:
        # Real-time calculation using FinancialService
        latest_snapshot = FinancialService.calculate_financials(user.organization)

    # Pagination for Transactions
    paginator = Paginator(transactions, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'financial_management.html', {
        'agents': agents,
        'latest_snapshot': latest_snapshot,
        'transactions': page_obj,
        'selected_date': selected_date_str
    })

@login_required
def cash_operation(request):
    if request.method == 'POST':
        op_type = request.POST.get('op_type')
        amount = int(request.POST.get('amount', 0))
        description = request.POST.get('description', '')
        
        if op_type == 'deposit':
             TransactionService.deposit(request.user.organization, amount, description)
        elif op_type == 'withdraw':
             TransactionService.withdraw(request.user.organization, amount, description)
             
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
        return redirect('approval_list')
        
    stocks = Stock.objects.all().order_by('name')
    return render(request, 'create_approval.html', {'stocks': stocks})

@login_required
def approval_list(request):
    agents = get_sidebar_agents(request.user)
    approvals = Approval.objects.filter(organization=request.user.organization).order_by('-created_at')
    return render(request, 'approval_list.html', {'agents': agents, 'approvals': approvals})

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
            approval.save()
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
                approved_at=log_date
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
                    description=f"승인된 매수: {approval.title}"
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
                    description=f"승인된 매도: {approval.title}"
                )
            
            create_daily_snapshot(request.user.organization.id)
            approval.status = 'approved'
            approval.save()
            return redirect('approval_list')
            
        elif action == 'reject':
            approval.status = 'rejected'
            approval.save()
            return redirect('approval_list')

    return render(request, 'approval_detail.html', {'agents': agents, 'approval': approval})

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
            if len(names) > 3:
                stock_list_str = f"<div class='node-stock'>📈 {', '.join(names[:2])} 외 {len(names)-2}종목</div>"
            else:
                stock_list_str = f"<div class='node-stock'>📈 {', '.join(names)}</div>"

        # Link to Admin (User Request: "connect to admin page")
        admin_link = f"<a href='/admin/core/agent/{agent.id}/change/' target='_blank' style='text-decoration:none; position:absolute; top:5px; right:5px; font-size:12px;'>⚙️</a>"

        rows.append([
            {'v': agent_id, 'f': f'<div class="node-card agent-card" style="position:relative;">{admin_link}<div class="img-circle">{img_html}</div><div class="node-name">{agent.name}</div><div class="node-role">{agent.position} / {agent.role}</div>{stock_list_str}</div>'},
            parent_id,
            agent.role
        ])

    return render(request, 'org_chart.html', {
        'agents': agents,
        'chart_data': json.dumps(rows)
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
        'current_direction': direction
    })

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

@login_required
def get_stock_detail(request):
    """
    AJAX view to get detailed stock info and candle data
    """
    stock_id = request.GET.get('stock_id')
    try:
        stock = Stock.objects.get(id=stock_id)
        
        # Determine ticker
        ticker_symbol = stock.code
        if stock.code.isdigit() and len(stock.code) == 6:
            ticker_symbol = f"{stock.code}.KS"
            
        ticker = yf.Ticker(ticker_symbol)
        
        # 1. Fetch Data
        info = ticker.info
        fast_info = ticker.fast_info
        
        # Update Country if missing or invalid
        if not stock.country or stock.country in COUNTRY_MAP: # If it was stored as English before
             stock.country = identify_stock_country(ticker_symbol, info)
             stock.save()

        # Prices & Market Cap
        stock.current_price = fast_info.last_price
        
        mkt_cap = fast_info.market_cap
        if not mkt_cap:
            mkt_cap = info.get('marketCap')
        
        # [UPDATE] Use Naver for Meta Data (Domestic & World)
        # Prioritize Naver description
        naver_data = get_naver_stock_extra_info(stock.code, info.get('exchange', ''))
        if naver_data.get('market_cap'):
            mkt_cap = naver_data['market_cap']
        
        # Determine description priority: Naver first, then yfinance
        if naver_data.get('description'):
            stock.description = naver_data['description']
        else:
            stock.description = "" # Reset to allow yfinance fallback later
        
        if stock.is_korean:
            # [Fix] Update name as well if changed on Naver
            naver_name = get_naver_stock_name(stock.code)
            if naver_name:
                stock.name = naver_name
        
        stock.market_cap = mkt_cap
        
        stock.per = info.get('trailingPE')
        stock.pbr = info.get('priceToBook')
        
        # 52w High/Low (Try fast_info first)
        h52 = fast_info.year_high
        l52 = fast_info.year_low
        
        # Fallback to info if fast_info is None/0
        if not h52: h52 = info.get('fiftyTwoWeekHigh')
        if not l52: l52 = info.get('fiftyTwoWeekLow')
        
        stock.high_52w = h52
        stock.low_52w = l52

        # [UPDATE] Name Correction for Korean Stocks (Naver)
        if stock.is_korean:
            kor_name = get_naver_stock_name(stock.code)
            if kor_name and kor_name != stock.name:
                stock.name = kor_name

        # [Fallback] If Naver description is missing, use yfinance + translation
        # [REMOVED] User requested to remove yfinance description fallback
        # if not stock.description:
        #     desc = info.get('longBusinessSummary') or info.get('description', '') ...
        
        stock.save()
        
        # Candle Data (3 Years, Weekly)
        hist = ticker.history(period="3y", interval="1wk")
        candles = []
        for date, row in hist.iterrows():
            candles.append({
                'x': date.strftime('%Y-%m-%d'),
                'y': [row['Open'], row['High'], row['Low'], row['Close']]
            })
        stock.candle_data = candles
        stock.save()
        
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

def get_naver_stock_name(code):
    """
    Fetch Korean stock name from Naver Finance
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Naver Finance structure: .wrap_company h2 a
        name_tag = soup.select_one('.wrap_company h2 a')
        if name_tag:
            return name_tag.text.strip()
            
    except Exception as e:
        print(f"Error fetching Naver name for {code}: {e}")
    
    return None

def _scrape_naver_summary(url, timeout=5):
    """
    Helper to scrape summary from Naver Stock Details page (Domestic & World)
    Tries DOM selector first, then __NEXT_DATA__ JSON
    """
    try:
        import requests
        from bs4 import BeautifulSoup
        import json
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. Selector approach
        desc_tag = soup.select_one('div[class*="SummaryInfo_summary-text"]')
        if desc_tag:
            return desc_tag.get_text().replace('더보기', '').strip()
            
        # 2. JSON State approach (for ETFs/World sometimes)
        script_tag = soup.select_one('#__NEXT_DATA__')
        if script_tag:
            try:
                js_data = json.loads(script_tag.string)
                # Try common paths in Apollo State
                apollo_state = js_data.get('props', {}).get('pageProps', {}).get('__APOLLO_STATE__', {})
                for key, val in apollo_state.items():
                    if 'summary' in val:
                         return val['summary'].replace('더보기', '').strip()
            except: pass
            
    except Exception as e:
        print(f"Scrape summary failed for {url}: {e}")
        
    return None

def get_naver_stock_extra_info(code, exchange=''):
    """
    Scrape Market Cap and Description from Naver Finance (Domestic & World)
    """
    data = {'market_cap': None, 'description': None}
    try:
        import requests
        from bs4 import BeautifulSoup
        import re
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        if code.isdigit() and len(code) == 6:
            # --- Domestic Stock ---
            # 1. Market Cap (main page)
            url_main = f"https://finance.naver.com/item/main.naver?code={code}"
            res_main = requests.get(url_main, headers=headers, timeout=5)
            soup_main = BeautifulSoup(res_main.text, 'html.parser')
            
            mkt_sum_tag = soup_main.select_one('#_market_sum')
            if mkt_sum_tag:
                full_text = mkt_sum_tag.parent.get_text().replace(',', '').replace('\n', '').strip()
                total_eok = 0
                jo_match = re.search(r'(\d+)\s*조', full_text)
                eok_match = re.search(r'(\d+)\s*억원', full_text)
                if jo_match: total_eok += int(jo_match.group(1)) * 10000
                if eok_match: total_eok += int(eok_match.group(1))
                if total_eok > 0: data['market_cap'] = total_eok * 100000000

            # 2. Description
            url_desc = f"https://stock.naver.com/domestic/stock/{code}/price"
            desc = _scrape_naver_summary(url_desc)
            if desc:
                data['description'] = desc

            # Fallback to FnGuide (Only for domestic)
            if not data['description']:
                try:
                    fnguide_url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{code}"
                    res_fn = requests.get(fnguide_url, headers=headers, timeout=5)
                    soup_fn = BeautifulSoup(res_fn.text, 'html.parser')
                    biz_summary = soup_fn.select_one('#bizSummaryContent')
                    if biz_summary:
                        parts = biz_summary.find_all('li')
                        data['description'] = "\n".join([p.get_text().strip() for p in parts])
                except Exception:
                    pass

        else:
            # --- World Stock ---
            suffix = ""
            if exchange == 'NYQ': suffix = ".K"
            elif exchange == 'NMS': suffix = ".O"
            elif exchange == 'ASE': suffix = ".A"
            
            # Naver World Stock description
            candidates = [f"{code}{suffix}", code]
            if not suffix: candidates = [f"{code}.K", f"{code}.O", code]
            
            for ticker in candidates:
                url_desc = f"https://stock.naver.com/worldstock/stock/{ticker}/price"
                desc = _scrape_naver_summary(url_desc)
                if desc:
                    data['description'] = desc
                    break
                 
    except Exception as e:
        print(f"Error scraping Naver extra info for {code}: {e}")
        
    return data

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
        'accounts': accounts
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
        'current_direction': direction
    })
