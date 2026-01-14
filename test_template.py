import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.utils import number_to_hangul, format_approval_content

# Test Number Conversion
nums = [1000, 35000, 1500000, 123456789]
for n in nums:
    print(f"{n} -> {number_to_hangul(n)}")

# Test Template Generation
content = format_approval_content(
    stock_name="삼성전자",
    stock_code="005930",
    quantity=10,
    price=70000,
    total_amount=700000,
    trade_type='buy',
    reason="테스트 사유",
    include_attachment=True
)
print("\n[Template Test With Attachment]")
print(content)

content_ceo = format_approval_content(
    stock_name="SK하이닉스",
    stock_code="000660",
    quantity=5,
    price=130000,
    total_amount=650000,
    trade_type='buy',
    reason="CEO 직접 지시",
    include_attachment=False
)
print("\n[Template Test CEO (No Attachment)]")
print(content_ceo)
