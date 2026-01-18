import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt # Or handle in template
from django.contrib.auth.decorators import login_required

from django.utils import timezone
from .models import Stock, Strategy
from .services_backtest import BacktestEngine
from .utils_strategy import StrategyConfig

@login_required
def strategy_list_view(request):
    """
    Renders the list of user strategies.
    [Submenu: my_strategies]
    """
    my_strategies = request.user.strategies.all().order_by('-updated_at')
    return render(request, 'strategy_list.html', {
        'my_strategies': my_strategies,
        'active_main_menu': 'strategy',
        'active_sub_menu': 'list'
    })

@login_required
def strategy_builder_view(request, pk=None):
    """
    Renders the Strategy Builder.
    If pk is provided, loads that strategy.
    [Submenu: builder]
    """
    # Stocks for reference regarding ticker (optional, logical)
    stocks = Stock.objects.all().order_by('display_order', 'name')
    
    context = {
        'stocks': stocks,
        'active_main_menu': 'strategy',
        'active_sub_menu': 'builder',
        'strategy_id': pk
    }
    return render(request, 'strategy_builder.html', context)

@login_required
def backtest_runner_view(request):
    """
    Renders the Backtest Runner.
    [Submenu: runner]
    """
    stocks = Stock.objects.all().order_by('display_order', 'name')
    my_strategies = request.user.strategies.all().order_by('-updated_at')
    
    return render(request, 'backtest_runner.html', {
        'stocks': stocks,
        'my_strategies': my_strategies,
        'active_main_menu': 'strategy',
        'active_sub_menu': 'runner'
    })

@login_required
def save_strategy_api(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    try:
        data = json.loads(request.body)
        name = data.get('name')
        if not name:
            return JsonResponse({'success': False, 'error': '전략 이름은 필수입니다.'})
            
        strategy_id = data.get('strategy_id')
        logic = data.get('logic', {})
        ticker = data.get('ticker', '')

        if strategy_id:
            strategy = Strategy.objects.get(pk=strategy_id, user=request.user)
            strategy.name = name
            strategy.logic = logic
            strategy.ticker = ticker
            strategy.save()
            msg = "수정되었습니다."
        else:
            strategy = Strategy.objects.create(
                user=request.user,
                name=name,
                logic=logic,
                ticker=ticker
            )
            msg = "저장되었습니다."
            
        return JsonResponse({'success': True, 'message': msg, 'strategy_id': strategy.id})
    except Strategy.DoesNotExist:
        return JsonResponse({'success': False, 'error': '전략을 찾을 수 없습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def list_strategies_api(request):
    strategies = request.user.strategies.values('id', 'name', 'ticker', 'updated_at').order_by('-updated_at')
    return JsonResponse({'success': True, 'data': list(strategies)})

@login_required
def load_strategy_api(request, pk):
    try:
        strategy = Strategy.objects.get(pk=pk, user=request.user)
        return JsonResponse({
            'success': True, 
            'data': {
                'id': strategy.id,
                'name': strategy.name,
                'ticker': strategy.ticker,
                'logic': strategy.logic
            }
        })
    except Strategy.DoesNotExist:
        return JsonResponse({'success': False, 'error': '전략을 찾을 수 없습니다.'})

@login_required
def delete_strategy_api(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    try:
        strategy = Strategy.objects.get(pk=pk, user=request.user)
        strategy.delete()
        return JsonResponse({'success': True, 'message': '삭제되었습니다.'})
    except Strategy.DoesNotExist:
        return JsonResponse({'success': False, 'error': '전략을 찾을 수 없습니다.'})

@login_required
def run_backtest_api(request):
    """
    API Interface for running a backtest.
    Expects JSON body: { ticker: '...', strategy: {...}, capital: 10000000 }
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})

    try:
        data = json.loads(request.body)
        ticker_code = data.get('ticker')
        capital = float(data.get('capital', 10000000))
        strategy_logic = data.get('strategy', {})
        
        # 1. Validate Strategy Schema (Basic Pydantic Check)
        # Note: Frontend sends a dict, we can try to validate it
        # If invalid, BacktestEngine calls might fail later, but good to check early.
        try:
            StrategyConfig(**strategy_logic)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f"전략 설정 오류: {str(e)}"})

        # 2. Add '.KS' suffix for yfinance if Korean stock
        # Ideally, Stock model should handle this, but for now:
        # If code is numeric (e.g., 005930), add .KS
        ticker_symbol = ticker_code
        if ticker_code.isdigit():
             ticker_symbol = f"{ticker_code}.KS"

        # 3. Run Engine
        result = BacktestEngine.run(strategy_logic, ticker_symbol, capital)
        
        return JsonResponse({'success': True, 'data': result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})

import csv
from django.http import HttpResponse

@login_required
@csrf_exempt
def export_backtest_csv(request):
    """
    Reruns the backtest and returns a CSV file of the trade log.
    Expects POST form data with 'strategy_json' (str)
    """
    if request.method != 'POST':
        return HttpResponse("POST method required", status=405)

    try:
        # Form Data Parsing
        ticker = request.POST.get('ticker')
        capital = float(request.POST.get('capital', 10000000))
        strategy_str = request.POST.get('strategy_json')
        
        if not strategy_str:
            return HttpResponse("Missing strategy_json", status=400)
            
        strategy_logic = json.loads(strategy_str)
        
        # Validate (Optional)
        try:
            StrategyConfig(**strategy_logic)
        except:
            pass # Engine handles runtime errors, or we can catch here

        # Ticker Suffix
        ticker_symbol = ticker
        if ticker and ticker.isdigit():
             ticker_symbol = f"{ticker}.KS"

        # Run Engine
        result = BacktestEngine.run(strategy_logic, ticker_symbol, capital)
        trades = result.get('trades', [])

        # Create CSV Response
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f"backtest_result_{ticker}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        # Header
        writer.writerow(['Date', 'Ticker', 'Type', 'Price', 'Quantity', 'Amount', 'Fees', 'Balance'])
        
        # Rows
        for t in trades:
            writer.writerow([
                t['date'],
                t.get('ticker', ticker),
                t['type'],
                t['price'],
                t['quantity'],
                t['amount'],
                t.get('fees', 0),
                t['balance']
            ])
            
        return response

    except Exception as e:
        return HttpResponse(f"Error generating CSV: {str(e)}", status=500)
