from django.db import transaction
from django.utils import timezone
from .models import Organization, Transaction, Stock
from django.db.models import Sum

class TransactionService:
    @staticmethod
    def create_transaction(organization, transaction_type, amount, related_asset=None, quantity=0, price=0, profit=0, fee=0, tax=0, description="", account=None, timestamp=None):
        """
        Creates a Transaction record and updates the Organization's cash balance atomically.
        """
        with transaction.atomic():
            # Refresh organization to prevent race conditions
            org = Organization.objects.select_for_update().get(id=organization.id)
            
            # Update Cash Balance
            # Note: 'amount' should be signed correctly before calling this.
            # e.g. Buy = negative amount, Sell = positive amount.
            org.cash_balance += amount
            org.save()
            
            # Create Transaction Record
            new_tx = Transaction.objects.create(
                organization=org,
                transaction_type=transaction_type,
                amount=amount,
                related_asset=related_asset,
                quantity=quantity,
                price=price,
                profit=profit,
                fee=fee, # [K-IFRS]
                tax=tax, # [K-IFRS]
                balance_after=org.cash_balance,
                description=description,
                timestamp=timestamp if timestamp else timezone.now(), # Use provided timestamp
                account=account 
            )
            
            return new_tx

    @staticmethod
    def deposit(organization, amount, description="Deposit"):
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        return TransactionService.create_transaction(
            organization=organization,
            transaction_type='DEPOSIT',
            amount=amount, # +
            description=description
        )

    @staticmethod
    def withdraw(organization, amount, description="Withdraw"):
        if amount <= 0:
            raise ValueError("Withdraw amount must be positive")
        return TransactionService.create_transaction(
            organization=organization,
            transaction_type='WITHDRAW',
            amount=-amount, # -
            description=description
        )

    @staticmethod
    def buy_stock(organization, stock, quantity, price, fee=0, description="Buy Stock", account=None, timestamp=None): # [K-IFRS] fee added
        # Cost = (Qty * Price) + Fee
        # But 'amount' in transaction is strictly cash flow.
        # If I pay 100 for stock and 1 for fee, total cash outflow is 101.
        # But commonly 'amount' for stock purchase is principal.
        # Let's define: amount = -(quantity * price + fee)
        # However, to keep it simple and consistent with previous logic:
        # Amount = - (Quantity * Price) - Fee
        cost_principal = quantity * price
        total_cost = cost_principal + fee
        
        return TransactionService.create_transaction(
            organization=organization,
            transaction_type='BUY',
            amount=-total_cost, # - (Principal + Fee)
            related_asset=stock,
            quantity=quantity, # + (Asset increases)
            price=price,
            fee=fee,
            description=description,
            account=account,
            timestamp=timestamp
        )

    @staticmethod
    def sell_stock(organization, stock, quantity, price, fee=0, tax=0, profit=0, description="Sell Stock", account=None, timestamp=None): # [K-IFRS] fee, tax added
        # Revenue = (Qty * Price) - Fee - Tax
        revenue_principal = quantity * price
        total_revenue = revenue_principal - fee - tax
        
        return TransactionService.create_transaction(
            organization=organization,
            transaction_type='SELL',
            amount=total_revenue, # + (Revenue - Deductions)
            related_asset=stock,
            quantity=-quantity, # - (Asset decreases)
            price=price,
            profit=profit,
            fee=fee,
            tax=tax,
            description=description,
            account=account,
            timestamp=timestamp
        )

class FinancialService:
    @staticmethod
    def calculate_financials(organization):
        """
        Calculates current financial statements based on the Transaction ledger.
        Returns a dictionary.
        """
        # 1. Cash (Source of Truth: Transaction Ledger)
        # We calculate cash strictly from transactions to ensure integrity.
        cash_aggregation = Transaction.objects.filter(organization=organization).aggregate(Sum('amount'))
        cash = cash_aggregation['amount__sum'] or 0

        # 2. Stock Holdings & Value
        holdings = {} # {stock_id: quantity}
        txs = Transaction.objects.filter(organization=organization)
        
        # Aggregates for K-IFRS
        total_buy_cost = 0 
        total_sell_revenue = 0
        total_realized_profit = 0
        
        total_deposit = 0
        total_withdraw = 0
        total_fees = 0
        total_taxes = 0

        for tx in txs:
             if tx.related_asset:
                 sid = tx.related_asset.id
                 holdings[sid] = holdings.get(sid, 0) + tx.quantity
             
             # Fee & Tax Accumulation (All transaction types)
             total_fees += tx.fee
             total_taxes += tx.tax

             if tx.transaction_type == 'BUY':
                 # Amount is negative for BUY. Principal part is abs(amount) - fee.
                 principal = abs(tx.amount) - tx.fee
                 total_buy_cost += principal
             
             elif tx.transaction_type == 'SELL':
                 # Amount is positive. Revenue principal = amount + fee + tax
                 principal = tx.amount + tx.fee + tx.tax
                 total_sell_revenue += principal
                 total_realized_profit += tx.profit
                 
             elif tx.transaction_type == 'DEPOSIT':
                 total_deposit += tx.amount
             elif tx.transaction_type == 'WITHDRAW':
                 total_withdraw += abs(tx.amount)
        
        total_stock_value = 0
        for sid, qty in holdings.items():
            if qty > 0:
                try:
                    stock = Stock.objects.get(id=sid)
                    price = stock.current_price if stock.current_price else 0
                    total_stock_value += qty * price
                except Stock.DoesNotExist:
                    continue

        # 3. Income Statement (First, to get Net Income)
        # Cost of Goods Sold (approx) = Revenue - Realized Profit
        # Note: This implies 'profit' on transaction was calculated correctly (Revenue - Cost Basis).
        cogs = total_sell_revenue - total_realized_profit
        
        # Remaining Cost Basis = Total Buy Cost - COGS
        remaining_cost_basis = total_buy_cost - cogs
        
        # Unrealized P/L = Current Value - Remaining Cost Basis
        unrealized_pl = total_stock_value - remaining_cost_basis
        
        realized_pl = total_realized_profit
        
        # [K-IFRS Logic]
        # Net Income (Performance) = (Realized + Unrealized) - (Fees + Taxes)
        gross_profit = realized_pl + unrealized_pl
        raw_net_income = gross_profit - total_fees - total_taxes

        # 4. K-IFRS Balance Sheet
        
        # Priority Logic: 
        # 1. Withdrawals are taken from Retained Earnings (if positive).
        # 2. Remaining Withdrawals are taken from Capital Stock.
        
        remaining_withdrawals = total_withdraw
        
        # Calculate Retained Earnings (Bucket available for withdrawal)
        # We start with the full Net Income.
        if raw_net_income > 0:
            deduction_from_re = min(raw_net_income, remaining_withdrawals)
            final_retained_earnings = raw_net_income - deduction_from_re
            remaining_withdrawals -= deduction_from_re
        else:
            final_retained_earnings = raw_net_income
            # If Net Income is negative, we don't increase the loss with withdrawals.
            # All withdrawals must come from Capital.
        
        # Calculate Capital Stock
        # Capital Stock = Total Deposits - (Allocated Withdrawals)
        final_capital_stock = total_deposit - remaining_withdrawals
        
        # Total Equity Check
        total_assets = cash + total_stock_value
        total_liabilities = 0 
        total_equity = total_assets - total_liabilities

        return {
            'date': timezone.now().date(),
            'total_cash': cash,
            'total_stock_value': total_stock_value,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
            
            'capital_stock': final_capital_stock,
            'retained_earnings': final_retained_earnings,
            
            'realized_pl': realized_pl,
            'unrealized_pl': unrealized_pl,
            'total_fees': total_fees,
            'total_taxes': total_taxes,
            'net_income': raw_net_income # Income Statement shows 'Performance' regardless of withdrawals
        }

    @staticmethod
    def get_portfolio_data(organization, account=None):
        """
        Calculates portfolio holdings aggregated from transactions.
        Optional: specific account filtering.
        """
        portfolio_map = {}
        
        # Filter Transactions
        txs = Transaction.objects.filter(
            organization=organization, 
            related_asset__isnull=False
        )
        if account:
            txs = txs.filter(account=account)
            
        txs = txs.select_related('related_asset').order_by('timestamp')

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
                    'current_price': 0,
                    'eval_amount': 0,
                    'yield': 0,
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
                        cur_price = 0
                
                p['current_price'] = cur_price
                p['eval_amount'] = cur_price * p['quantity']
                # Adding formatted currency for display if needed purely in backend, but keep raw for template template tags
                
                # Yield
                if p['total_amount'] > 0:
                        p['yield'] = ((p['eval_amount'] - p['total_amount']) / p['total_amount']) * 100
                else:
                        p['yield'] = 0
                        
                portfolio_list.append(p)
        
        return portfolio_list
