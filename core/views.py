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
from django.http import JsonResponse, HttpResponse

from .models import Organization, DailySnapshot, Transaction, Stock, InterestStock, Agent, Message, Approval, InvestmentLog
from .services import TransactionService, FinancialService
from .tasks import create_approval_draft, create_daily_snapshot
from .utils import parse_mirae_sms

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
    
    # 1. 포트폴리오
    portfolio_qs = InvestmentLog.objects.filter(
        Q(agent__organization=user.organization) | Q(user__organization=user.organization), 
        status='approved'
    ).order_by('-approved_at')
    
    pf_paginator = Paginator(portfolio_qs, 5)
    pf_page_number = request.GET.get('pf_page')
    portfolio = pf_paginator.get_page(pf_page_number)
    
    for item in portfolio:
        try:
            code = item.stock_code
            current_price = 0
            if code and code.isdigit():
                ticker_symbol = f"{code}.KS" 
                ticker = yf.Ticker(ticker_symbol)
                info = ticker.fast_info
                current_price = info.last_price if info.last_price else 0
            
            item.current_price = current_price
            item.eval_amount = current_price * item.quantity
        except Exception:
            item.current_price = 0
            item.eval_amount = 0
    
    # Summary Calculation
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

    # 3. 운용 로그
    log_list = InvestmentLog.objects.filter(
        Q(agent__organization=user.organization) | Q(user__organization=user.organization),
        status='approved'
    ).order_by('-approved_at')
    
    paginator = Paginator(log_list, 5)
    page_number = request.GET.get('page')
    investment_logs = paginator.get_page(page_number)

    # AJAX logic
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        section = request.GET.get('section')
        if section == 'portfolio':
             return render(request, 'partials/portfolio_section.html', {'portfolio': portfolio})
        else:
             return render(request, 'partials/log_section.html', {'investment_logs': investment_logs})

    summary = {
        'count': total_count,
        'total_buy': total_buy_amount,
        'total_sell': 0,
        'principal': total_buy_amount,
        'eval_balance': total_buy_amount,
        'yield': 0.0,
        'yield_color': 'text-dark'
    }

    # Handle Draft Creation (Manual)
    if request.method == 'POST' and request.POST.get('action') == 'create_draft':
        stock_name = request.POST.get('stock_name')
        qty = int(request.POST.get('quantity', 0))
        amt = int(request.POST.get('total_amount', 0))
        
        # Simple Draft Creation logic
        # Assuming finding stock code logic is omitted or simplified
        stock_code = "UNKNOWN"
        stock_obj = Stock.objects.filter(name=stock_name).first()
        if stock_obj:
            stock_code = stock_obj.code
            
        Approval.objects.create(
            organization=user.organization,
            user=user,
            title=f"CEO 직접 지시: {stock_name} 매수",
            description=f"종목: {stock_name}, 수량: {qty}, 금액: {amt}",
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
        'all_stocks': Stock.objects.all().order_by('name')
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
        if action == 'approve':
            # Create Investment Log
            new_log = InvestmentLog.objects.create(
                user=approval.user if approval.user else None,
                agent=approval.agent if approval.agent else None,
                stock_name=approval.temp_stock_name,
                stock_code=approval.temp_stock_code,
                quantity=approval.temp_quantity,
                total_amount=approval.temp_total_amount,
                status='approved',
                approved_at=timezone.now()
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
    agents = get_sidebar_agents(request.user)
    return render(request, 'org_chart.html', {'agents': agents})

@method_decorator(csrf_exempt, name='dispatch')
class SmsWebhookView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            secret_key = data.get('secret_key')
            content = data.get('content')
            
            # Simple UserProfile check
            from .models import UserProfile
            profile = UserProfile.objects.filter(secret_key=secret_key).first()
            if not profile: return HttpResponse("Unauthorized", status=401)
            
            parsed = parse_mirae_sms(content)
            if parsed:
                # Create Pending Approval Logic
                # (Skipping detail implementation to focus on core)
                pass
                
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# [NEW] Stock Management Views
@login_required
def stock_management(request):
    user = request.user
    agents = get_sidebar_agents(user)
    # [UPDATE] Fetch ALL stocks (Global List)
    stocks = Stock.objects.all().order_by('name')
    return render(request, 'stock_management.html', {
        'agents': agents,
        'stocks': stocks
    })

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
                    
                    # [UPDATE] Try Naver for Korean Name
                    if db_code.isdigit() and len(db_code) == 6:
                        naver_name = get_naver_stock_name(db_code)
                        if naver_name:
                            stock_name = naver_name

                    stock, created = Stock.objects.get_or_create(
                        code=db_code,
                        defaults={
                            'name': stock_name,
                            'current_price': current_price
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
        
        # Prices & Market Cap
        stock.current_price = fast_info.last_price
        
        # Try fast_info for market_cap first (more reliable)
        mkt_cap = fast_info.market_cap
        if not mkt_cap:
            mkt_cap = info.get('marketCap')
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

        # Description Translation
        desc = info.get('longBusinessSummary') or info.get('description', '')
        if desc:
            try:
                from googletrans import Translator
                translator = Translator()
                # Translate to Korean
                translated = translator.translate(desc, dest='ko').text
                stock.description = translated
            except Exception as e:
                # Fallback to English if translation fails (e.g. no internet, or lib issue)
                # print(f"Translation failed: {e}")
                stock.description = desc
        
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
