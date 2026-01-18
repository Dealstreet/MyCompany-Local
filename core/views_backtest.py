import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt # Or handle in template
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from .models import Stock
from .services_backtest import BacktestEngine
from .utils_strategy import StrategyConfig

@staff_member_required
def backtest_dashboard(request):
    """
    Renders the Strategy Builder UI.
    """
    # Fetch all stocks for the dropdown
    stocks = Stock.objects.all().order_by('display_order', 'name')
    stocks = Stock.objects.all().order_by('display_order', 'name')
    return render(request, 'backtest_dashboard.html', {
        'stocks': stocks,
        'active_main_menu': 'strategy',
        'active_sub_menu': 'backtest'
    })

@staff_member_required
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

@staff_member_required
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
