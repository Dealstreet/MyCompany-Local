import yfinance as yf
from django.core.management.base import BaseCommand
from core.models import Stock

COUNTRY_MAP = {
    'South Korea': '한국',
    'United States': '미국',
    'Japan': '일본',
    'China': '중국',
    'Hong Kong': '홍콩',
    'Taiwan': '대만',
}

class Command(BaseCommand):
    help = 'Update country information for all existing stocks'

    def handle(self, *args, **options):
        stocks = Stock.objects.all()
        self.stdout.write(f"Starting update for {stocks.count()} stocks...")
        
        success_count = 0
        fail_count = 0

        for stock in stocks:
            try:
                ticker_symbol = stock.code
                if stock.code.isdigit() and len(stock.code) == 6:
                    ticker_symbol = f"{stock.code}.KS"
                
                ticker = yf.Ticker(ticker_symbol)
                info = ticker.info
                
                # Try to get country from info
                country_en = info.get('country', '')
                country_ko = ""
                
                if country_en:
                    country_ko = COUNTRY_MAP.get(country_en, country_en)
                
                # Fallback logic based on ticker symbol or exchange
                if not country_ko:
                    if ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ'):
                        country_ko = "한국"
                    elif '.' not in ticker_symbol:
                        # US stocks usually don't have a dot suffix in yfinance common tickers
                        country_ko = "미국"
                    else:
                        exchange = info.get('exchange', '')
                        if exchange in ['NMS', 'NYQ', 'ASE', 'NGM', 'NCM', 'PCX']:
                            country_ko = "미국"
                        elif exchange in ['KSC', 'KOE']:
                            country_ko = "한국"
                
                if country_ko:
                    stock.country = country_ko
                    stock.save()
                    self.stdout.write(self.style.SUCCESS(f"Successfully updated {stock.name} ({stock.code}) -> {country_ko}"))
                    success_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"No country info found for {stock.name} ({stock.code})"))
                    fail_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to update {stock.name} ({stock.code}): {e}"))
                fail_count += 1

        self.stdout.write(self.style.SUCCESS(f"Finished! Success: {success_count}, Fail: {fail_count}"))
