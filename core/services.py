from django.db import transaction
from django.utils import timezone
from .models import Organization, Transaction, Stock
from django.db.models import Sum

class TransactionService:
    @staticmethod
    def create_transaction(organization, transaction_type, amount, related_asset=None, quantity=0, price=0, profit=0, fee=0, tax=0, description=""):
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
                timestamp=timezone.now()
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
    def buy_stock(organization, stock, quantity, price, fee=0, description="Buy Stock"): # [K-IFRS] fee added
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
            description=description
        )

    @staticmethod
    def sell_stock(organization, stock, quantity, price, fee=0, tax=0, profit=0, description="Sell Stock"): # [K-IFRS] fee, tax added
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
            description=description
        )

class FinancialService:
    @staticmethod
    def calculate_financials(organization):
        """
        Calculates current financial statements based on the Transaction ledger.
        Returns a dictionary.
        """
        # 1. Cash (Source of Truth: Organization Model)
        cash = organization.cash_balance

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
                 principal = abs(tx.amount) - tx.fee
                 total_buy_cost += principal
             
             elif tx.transaction_type == 'SELL':
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
        cogs = total_sell_revenue - total_realized_profit
        remaining_cost_basis = total_buy_cost - cogs
        
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
