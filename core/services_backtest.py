import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
from django.utils import timezone

# Configure Logger
logger = logging.getLogger(__name__)

class MarketDataService:
    @staticmethod
    def fetch_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """
        Fetches OHLCV data using yfinance.
        """
        try:
            # yfinance download
            df = yf.download(ticker, period=period, interval=interval, progress=False, multi_level_index=False)
            if df.empty:
                raise ValueError(f"No data found for {ticker}")
            
            # Ensure standard column names
            # yfinance usually returns: Open, High, Low, Close, Adj Close, Volume
            # Verify and rename if needed
            return df
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            raise

class TechnicalAnalysis:
    @staticmethod
    def add_indicators(df: pd.DataFrame, indicators: List[Dict]) -> pd.DataFrame:
        """
        Adds technical indicators to the DataFrame.
        indicators example: [{'name': 'RSI', 'params': {'period': 14}}, {'name': 'SMA', 'params': {'period': 20}}]
        """
        df = df.copy()
        for ind in indicators:
            name = ind['name'].upper()
            params = ind.get('params', {})
            
            if name == 'SMA':
                period = int(params.get('period', 20))
                df[f'SMA_{period}'] = df['Close'].rolling(window=period).mean()
            
            elif name == 'EMA':
                period = int(params.get('period', 20))
                df[f'EMA_{period}'] = df['Close'].ewm(span=period, adjust=False).mean()

            elif name == 'RSI':
                period = int(params.get('period', 14))
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                df[f'RSI_{period}'] = 100 - (100 / (1 + rs))
            
            elif name == 'MACD':
                fast = int(params.get('fast', 12))
                slow = int(params.get('slow', 26))
                signal = int(params.get('signal', 9))
                
                exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
                exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
                macd = exp1 - exp2
                signal_line = macd.ewm(span=signal, adjust=False).mean()
                
                df[f'MACD_{fast}_{slow}'] = macd
                df[f'MACD_Signal_{signal}'] = signal_line
                df[f'MACD_Hist'] = macd - signal_line

            elif name == 'BB': # Bollinger Bands
                period = int(params.get('period', 20))
                std_dev = float(params.get('std_dev', 2.0))
                sma = df['Close'].rolling(window=period).mean()
                std = df['Close'].rolling(window=period).std()
                
                df[f'BB_Upper_{period}'] = sma + (std * std_dev)
                df[f'BB_Lower_{period}'] = sma - (std * std_dev)
                # Middle band is essentially SMA
                
        return df

class ConditionEvaluator:
    @staticmethod
    def get_series(df: pd.DataFrame, item: Dict) -> pd.Series:
        """
        Resolves a value (LHS/RHS) to a pandas Series.
        item example: {'type': 'INDICATOR', 'name': 'RSI', 'params': {'period': 14}}
                      or {'type': 'STATIC', 'value': 30}
        """
        # Note: The data structure from Pydantic model 'Condition' maps slightly differently.
        # We assume the "Logic" JSON has processed or is matching:
        # Pydantic: value_type='STATIC', value=30
        # This Helper assumes inputs based on that schema.
        
        # If passed a direct float/int
        if isinstance(item, (int, float)):
           return pd.Series(item, index=df.index)

        # If it's a Pydantic-like dict
        v_type = item.get('value_type', 'STATIC')
        
        if v_type == 'STATIC':
            val = item.get('value')
            return pd.Series(val, index=df.index)
        
        elif v_type == 'INDICATOR':
            # Construct column name
            ind_config = item.get('indicator', item.get('value')) # Handle nested structure
            if isinstance(ind_config, dict):
                name = ind_config.get('name')
                params = ind_config.get('params', {})
            else:
                # Fallback or error
                logger.error(f"Invalid indicator config: {ind_config}")
                return pd.Series(0, index=df.index)

            col_name = None
            if name == 'RSI':
                col_name = f"RSI_{params.get('period', 14)}"
            elif name == 'SMA':
                col_name = f"SMA_{params.get('period', 20)}"
            elif name == 'EMA':
                col_name = f"EMA_{params.get('period', 20)}"
            elif name == 'PRICE': # Close Price
                col_name = "Close"
            elif name == 'VOLUME':
                col_name = "Volume"
            
            if col_name and col_name in df.columns:
                return df[col_name]
            else:
                # If column missing, maybe try on-the-fly calc or 0
                logger.warning(f"Column {col_name} missing. Returning 0.")
                return pd.Series(0, index=df.index)

    @staticmethod
    def evaluate_node(df: pd.DataFrame, node: Dict) -> pd.Series:
        """
        Recursively evaluates LogicNode. Returns boolean Series (mask).
        """
        connector = node.get('connector', 'AND')
        conditions = node.get('conditions', [])
        is_not = node.get('not_logic', False)
        
        if not conditions:
            # If empty conditions, what is default? True?
            return pd.Series(True, index=df.index)

        # Evaluate first child
        if 'connector' in conditions[0]: # Nested Group
            mask = ConditionEvaluator.evaluate_node(df, conditions[0])
        else: # Leaf Condition
            mask = ConditionEvaluator.evaluate_condition(df, conditions[0])
            
        for i in range(1, len(conditions)):
            child = conditions[i]
            if 'connector' in child:
                child_mask = ConditionEvaluator.evaluate_node(df, child)
            else:
                child_mask = ConditionEvaluator.evaluate_condition(df, child)
            
            if connector == 'AND':
                mask = mask & child_mask
            elif connector == 'OR':
                mask = mask | child_mask
        
        if is_not:
            mask = ~mask
            
        return mask

    @staticmethod
    def evaluate_condition(df: pd.DataFrame, cond: Dict) -> pd.Series:
        lhs = ConditionEvaluator.get_series(df, {'value_type': 'INDICATOR', 'indicator': cond.get('indicator')})
        
        # RHS handling
        rhs_input = cond.get('value')
        rhs_type = cond.get('value_type', 'STATIC')
        
        # If rhs_input itself is dict (IndicatorConfig) and type is INDICATOR
        if rhs_type == 'INDICATOR':
            rhs = ConditionEvaluator.get_series(df, {'value_type': 'INDICATOR', 'indicator': rhs_input})
        else:
            rhs = ConditionEvaluator.get_series(df, {'value_type': 'STATIC', 'value': rhs_input})

        op = cond.get('operator')
        
        if op == '>':
            return lhs > rhs
        elif op == '<':
            return lhs < rhs
        elif op == '>=':
            return lhs >= rhs
        elif op == '<=':
            return lhs <= rhs
        elif op == '=':
            return lhs == rhs
        elif op == 'CROSS_UP':
            # (Previous LHS < Previous RHS) AND (Current LHS > Current RHS)
            prev_lhs = lhs.shift(1)
            prev_rhs = rhs.shift(1)
            return (prev_lhs < prev_rhs) & (lhs > rhs)
        elif op == 'CROSS_DOWN':
            prev_lhs = lhs.shift(1)
            prev_rhs = rhs.shift(1)
            return (prev_lhs > prev_rhs) & (lhs < rhs)
            
        return pd.Series(False, index=df.index)


class BacktestEngine:
    @staticmethod
    def run(strategy_json: Dict, ticker: str, initial_capital: float = 10000000) -> Dict:
        # 1. Fetch Data
        df = MarketDataService.fetch_ohlcv(ticker)
        
        # 2. Extract Indicators needed (Pre-pass)
        # For simplicity, we assume we just calculate ALL common indicators or parse logic to find them.
        # Let's add standard set for now.
        inds = [
            {'name': 'SMA', 'params': {'period': 5}},
            {'name': 'SMA', 'params': {'period': 20}},
            {'name': 'SMA', 'params': {'period': 60}},
            {'name': 'RSI', 'params': {'period': 14}},
            {'name': 'MACD', 'params': {}},
            {'name': 'BB', 'params': {'period': 20, 'std_dev': 2}}
        ]
        df = TechnicalAnalysis.add_indicators(df, inds)
        df = df.dropna()

        # 3. Signals
        buy_logic = strategy_json.get('buy_conditions', {})
        buy_mask = ConditionEvaluator.evaluate_node(df, buy_logic)
        
        sell_logic = strategy_json.get('sell_conditions', {})
        if sell_logic:
            sell_mask = ConditionEvaluator.evaluate_node(df, sell_logic)
        else:
            sell_mask = pd.Series(False, index=df.index)

        # 4. Simulation Loop (Vectorized logic is hard for position sizing + cash constraints, so loop)
        cash = initial_capital
        holdings = 0
        trades = []
        equity_curve = []
        
        dates = df.index
        closes = df['Close'].values
        opens = df['Open'].values # Can simulate buy on Open of NEXT day? Or Close of current day? 
        # Standard: Signals calc on Close, Trade on NEXT Open. 
        # For simplicity -> Trade on Close of Today (Assumption: Signal known at 3:30pm)
        
        # Convert masks to boolean arrays for speed
        buy_arr = buy_mask.values
        sell_arr = sell_mask.values
        
        dca_config = strategy_json.get('dca_config', {})
        dca_enabled = dca_config.get('enabled', False)
        dca_amount = float(dca_config.get('amount', 0))
        dca_interval = dca_config.get('interval', 'monthly')
        
        last_dca_date = None

        for i in range(len(df)):
            date = dates[i]
            price = closes[i]
            
            # Position Value
            equity = cash + (holdings * price)
            
            # --- DCA Logic ---
            if dca_enabled:
                do_dca = False
                if dca_interval == 'monthly':
                    if last_dca_date is None or date.month != last_dca_date.month:
                        do_dca = True
                        last_dca_date = date
                elif dca_interval == 'weekly':
                    # Simplified
                    if last_dca_date is None or (date - last_dca_date).days >= 7:
                        do_dca = True
                        last_dca_date = date
                
                if do_dca and cash >= dca_amount:
                    qty = int(dca_amount // price)
                    if qty > 0:
                        cost = qty * price
                        cash -= cost
                        holdings += qty
                        trades.append({
                            'date': date.strftime('%Y-%m-%d'),
                            'ticker': ticker,
                            'type': 'BUY_DCA',
                            'price': price,
                            'quantity': qty,
                            'amount': cost,
                            'fees': 0, # TODO: Add fee calc
                            'balance': cash
                        })

            # --- Strategy Logic ---
            if buy_arr[i]:
                # Buy Signal: Buy with % of cash or fixed?
                # Default behavior: All In (Simple) or Fixed Amount
                # Let's assume usage of available cash (max 95%)
                if cash > price:
                    invest_amt = cash * 0.99 
                    qty = int(invest_amt // price)
                    if qty > 0:
                        cost = qty * price
                        cash -= cost
                        holdings += qty
                        trades.append({
                            'date': date.strftime('%Y-%m-%d'),
                            'ticker': ticker,
                            'type': 'BUY_SIGNAL',
                            'price': price,
                            'quantity': qty,
                            'amount': cost,
                            'fees': 0,
                            'balance': cash
                        })
            
            elif sell_arr[i]:
                if holdings > 0:
                    revenue = holdings * price
                    cash += revenue
                    trades.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'ticker': ticker,
                        'type': 'SELL_SIGNAL',
                        'price': price,
                        'quantity': holdings,
                        'amount': revenue,
                        'fees': 0,
                        'balance': cash
                    })
                    holdings = 0
            
            # Recalc equity after trade
            equity = cash + (holdings * price)
            equity_curve.append({'date': date.strftime('%Y-%m-%d'), 'equity': equity})

        # 5. Metrics
        final_equity = equity_curve[-1]['equity']
        total_return = ((final_equity - initial_capital) / initial_capital) * 100
        
        # MDD
        eq_series = pd.Series([e['equity'] for e in equity_curve])
        peak = eq_series.cummax()
        drawdown = (eq_series - peak) / peak
        mdd = drawdown.min() * 100 # %

        # Win Rate & Profit Factor
        winning_trades = 0
        losing_trades = 0
        total_win_amt = 0
        total_loss_amt = 0

        # We need to link Sells to Buys to calculate profit per trade.
        # Current logic just logs Buy/Sell independently. 
        # Approximate by checking realized profit on SELL events?
        # Current 'SELL' log format: type='SELL_SIGNAL', quantity=..., amount=... (Revenue)
        # To get profit, we need avg_cost.
        # Let's simple-track avg_cost during the loop or post-process.
        # But wait, the loop didn't track "Profit per Trade". 
        
        # Refactoring loop to track trade profit for KPI
        # Since we just need summary stats, let's just count 'Realized Profit' if possible.
        # But 'trades' list currently only has revenue (amount) for sells.
        # We need to know the cost basis.
        
        # Quick Fix: Let's assume FIFO or Avg Cost. Since we sell ALL ('holdings = 0'), 
        # profit = Revenue - (AvgPrice * Qty).
        # We need to track avg_price during buys.
        
        # Let's re-iterate the trades list to calculate Profit/Loss
        trade_pnl = []
        
        # Reconstruction of PnL from the linear trade log
        # This is a bit tricky if we have multiple buys then one sell.
        # We can implement a simple queue or weighted average tracking.
        
        # Simplified Avg Cost Tracking
        current_qty = 0
        total_cost = 0
        
        processed_trades = [] # Enhanced trades with PnL
        
        for t in trades:
            if 'BUY' in t['type']:
                qty = t['quantity']
                cost = t['amount']
                total_cost += cost
                current_qty += qty
                processed_trades.append(t)
            
            elif 'SELL' in t['type']:
                sell_qty = t['quantity']
                revenue = t['amount']
                
                if current_qty > 0:
                    avg_cost = total_cost / current_qty
                    cost_basis = avg_cost * sell_qty
                    pnl = revenue - cost_basis
                    trade_pnl.append(pnl)
                    
                    t['pnl'] = pnl # Add pnl to trade log
                    t['pnl_percent'] = (pnl / cost_basis) * 100 if cost_basis > 0 else 0
                    
                    # Update tracking
                    total_cost -= cost_basis
                    current_qty -= sell_qty
                else:
                    t['pnl'] = 0
                    
                processed_trades.append(t)

        # KPI Calc
        wins = [p for p in trade_pnl if p > 0]
        losses = [p for p in trade_pnl if p <= 0]
        
        win_rate = (len(wins) / len(trade_pnl) * 100) if trade_pnl else 0
        
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999 if gross_profit > 0 else 0)

        return {
            'ticker': ticker,
            'initial_capital': initial_capital,
            'final_equity': final_equity,
            'total_return': total_return,
            'mdd': mdd,
            'win_rate': win_rate,     # New
            'profit_factor': profit_factor, # New
            'trade_count': len(trade_pnl),  # Completed trades (Round trips)
            'trades': processed_trades,     # Updated with PnL
            'equity_curve': equity_curve
        }
