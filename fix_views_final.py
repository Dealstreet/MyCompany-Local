
import os
from django.shortcuts import render, redirect, get_object_or_404 # Ensure these are available if used in snippet? They are already imported in top of views.py

file_path = 'core/views.py'
target_line_part = "return JsonResponse({'error': str(e), 'quotes': []})"
append_content = """

@login_required
def account_management(request):
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
                acc.delete()
        
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
"""

with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

cutoff = -1
for i, line in enumerate(lines):
    if target_line_part in line:
        cutoff = i
        break

if cutoff != -1:
    print(f"Truncating file at line {cutoff+1}")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines[:cutoff+1])
        f.write(append_content)
else:
    print("Target line not found, no truncation performed.")
