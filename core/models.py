from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from .utils import generate_employee_id

# 1. 회사 (Organization)
class Organization(models.Model):
    name = models.CharField(max_length=100, verbose_name="회사명")
    description = models.TextField(blank=True, verbose_name="회사 설명")
    cash_balance = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="현금 잔고") # [New]
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# 1-1. 부서 (Department) - 조직도 관리를 위한 모델
class Department(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, verbose_name="소속 회사")
    name = models.CharField(max_length=50, verbose_name="부서명")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='sub_departments', verbose_name="상위 부서")
    
    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


# 2. 사람 (User) - 사번 및 직급 필드 포함 커스텀 유저
class User(AbstractUser):
    ROLE_CHOICES = [('ceo', '사장'), ('staff', '직원')]
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, verbose_name="소속 회사")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff', verbose_name="직책")
    
    # 인사 관리 및 시스템 식별을 위한 사번/직급
    employee_id = models.CharField(max_length=20, unique=True, verbose_name="사번", null=True, blank=True)
    position = models.CharField(max_length=50, verbose_name="직급", null=True, blank=True)

    # 모델 충돌 방지를 위한 related_name 설정
    groups = models.ManyToManyField(
        'auth.Group', related_name='core_user_set', blank=True,
        help_text='The groups this user belongs to.', verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', related_name='core_user_set', blank=True,
        help_text='Specific permissions for this user.', verbose_name='user permissions',
    )

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = generate_employee_id()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.employee_id if self.employee_id else 'No ID'})"

# 3. AI 직원 (Agent) - 관리 종목(Ticker) 매핑
class Agent(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='agents', verbose_name="소속 회사")
    
    name = models.CharField(max_length=50, verbose_name="이름")
    department_obj = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='agents', verbose_name="소속 부서 (연동)")
    position = models.CharField(max_length=50, default='실장', verbose_name="직급")
    role = models.CharField(max_length=100, verbose_name="담당 업무")
    role = models.CharField(max_length=100, verbose_name="담당 업무")
    persona = models.TextField(verbose_name="프롬프트(페르소나)")
    model_name = models.CharField(max_length=50, default='gpt-5-nano', verbose_name="사용 모델")
    profile_image = models.ImageField(upload_to='agents/', null=True, blank=True, verbose_name="프로필 이미지")
    # [추가] 통합 사번 (YYYYNNN)
    employee_id = models.CharField(max_length=20, unique=True, verbose_name="사번", null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = generate_employee_id()
        super().save(*args, **kwargs)

    def __str__(self):
        dept = self.department_obj.name if self.department_obj else "소속미정"
        return f"{dept} {self.name} {self.position} ({self.role})"

# 4. 투자 로그 (InvestmentLog) - 최종 승인 시 생성되는 실제 자산 기록
class InvestmentLog(models.Model):
    STATUS_CHOICES = [
        ('approved', '승인완료'),
        ('rejected', '반려'),
    ]

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, null=True, blank=True, verbose_name="담당 AI 직원")
    
    # [신규] 출처 및 사용자
    SOURCE_CHOICES = [('ceo', '👑 CEO'), ('sms', '📱 SMS')]
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='ceo', verbose_name="출처")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="사용자", null=True, blank=True)
    account = models.ForeignKey('Account', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="매수 계좌") # [New]
    order_no = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="주문번호") # 중복방지

    stock_name = models.CharField(max_length=50, verbose_name="종목명", null=True, blank=True)
    stock_code = models.CharField(max_length=20, verbose_name="종목코드", null=True, blank=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, verbose_name="거래금액")
    quantity = models.IntegerField(verbose_name="수량")
    
    avg_price = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="평균단가", null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='approved')
    
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # 평균단가 자동 계산
        if self.total_amount and self.quantity and self.quantity != 0:
            self.avg_price = abs(self.total_amount / self.quantity)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_source_display()}] {self.stock_name} ({self.quantity}주)"

# 5. 전자결재 문서 (Approval) - 기안 및 임시 데이터 보관
class Approval(models.Model):
    REPORT_TYPES = [
        ('buy', '매수보고'),
        ('sell', '매도보고'),
        ('perf', '성과보고'),
        ('market', '시장보고'),
        ('gen', '일반기안'),
    ]
    STATUS_CHOICES = [
        ('draft', '임시저장'), 
        ('pending', '결재대기'),
        ('approved', '최종승인'),
        ('rejected', '반려됨'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    drafter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='drafted_approvals', verbose_name="사람 기안자")
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='drafted_approvals', verbose_name="AI 기안자")
    
    # 보고 유형 및 가변 정보 저장용 임시 필드
    report_type = models.CharField(max_length=10, choices=REPORT_TYPES, default='gen', verbose_name="보고 유형")
    temp_stock_name = models.CharField(max_length=50, null=True, blank=True, verbose_name="임시 종목명") # [추가]
    temp_stock_code = models.CharField(max_length=20, null=True, blank=True, verbose_name="임시 종목코드")
    temp_total_amount = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, verbose_name="임시 거래금액")
    temp_quantity = models.IntegerField(null=True, blank=True, verbose_name="임시 수량")
    temp_account = models.ForeignKey('Account', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="임시 매수 계좌") # [New]
    
    # [추가] 날짜 및 기간 필드
    temp_date = models.DateField(null=True, blank=True, verbose_name="거래/분석 일자")
    temp_start_date = models.DateField(null=True, blank=True, verbose_name="성과 시작일")
    temp_end_date = models.DateField(null=True, blank=True, verbose_name="성과 종료일")
    temp_extra_info = models.TextField(null=True, blank=True, verbose_name="추가 상세내용")

    title = models.CharField(max_length=200, verbose_name="문서 제목")
    content = models.TextField(verbose_name="문서 내용")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="문서 상태")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 최종 승인 후 생성된 로그와 연결
    investment_log = models.OneToOneField(InvestmentLog, on_delete=models.SET_NULL, null=True, blank=True, related_name='approval_doc')

    def __str__(self):
        return f"[{self.get_report_type_display()}] {self.title}"

# 6. 업무 (Task)
class Task(models.Model):
    STATUS_CHOICES = [('pending', '대기'), ('processing', '진행'), ('completed', '완료'), ('failed', '실패')]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tasks', verbose_name="지시자")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='tasks', verbose_name="담당 AI")
    title = models.CharField(max_length=200, verbose_name="업무 제목")
    content = models.TextField(verbose_name="지시 내용")
    result = models.TextField(null=True, blank=True, verbose_name="AI 결과물")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# 7. 결재 라인 (ApprovalLine)
class ApprovalLine(models.Model):
    STATUS_CHOICES = [('pending', '대기'), ('current', '검토중'), ('approved', '승인'), ('rejected', '반려')]

    approval = models.ForeignKey(Approval, on_delete=models.CASCADE, related_name='lines', verbose_name="결재문서")
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='approvals_to_review', verbose_name="결재자")
    step = models.IntegerField(default=1, verbose_name="결재 순서")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="결재 상태")
    comment = models.TextField(null=True, blank=True, verbose_name="검토 의견")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['step']

# 8. 메신저 대화 기록 (Message)
class Message(models.Model):
    ROLE_CHOICES = [('user', '사장님'), ('assistant', 'AI 직원')]

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(verbose_name="내용")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

# 9. 종목 정보 (Stock)
class Stock(models.Model):
    name = models.CharField(max_length=100, verbose_name="종목명")
    code = models.CharField(max_length=20, unique=True, verbose_name="종목코드")
    current_price = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True, verbose_name="현재가")
    high_52w = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True, verbose_name="52주 고가")
    low_52w = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True, verbose_name="52주 저가")
    candle_data = models.JSONField(default=list, verbose_name="캔들 데이터(종가)")
    
    # [New] Metadata
    market_cap = models.BigIntegerField(null=True, blank=True, verbose_name="시가총액")
    per = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="PER")
    pbr = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="PBR")
    description = models.TextField(blank=True, verbose_name="기업 개요")
    country = models.CharField(max_length=50, blank=True, verbose_name="국가")
    display_order = models.IntegerField(default=0, verbose_name="표시 순서")
    
    # [Refactor] Agent가 여러 종목을 관리하므로 관계를 Stock 쪽으로 이동
    agent = models.ForeignKey('Agent', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_stocks', verbose_name="담당 AI")

    updated_at = models.DateTimeField(auto_now=True, verbose_name="최근 업데이트")

    @property
    def is_korean(self):
        return self.country in ['한국', 'Korea', 'South Korea', 'KR']

    def __str__(self):
        return f"{self.name} ({self.code})"

class TradeNotification(models.Model):
    """
    미래에셋증권 등 외부 체결 알림(SMS) 원본 로그 저장
    """
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='notifications')
    content = models.TextField(verbose_name="SMS 원본 내용")
    
    # Parsed Data (Optional, if parsing succeeds)
    stock_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="종목명")
    stock_code = models.CharField(max_length=20, null=True, blank=True, verbose_name="종목코드")
    trade_type = models.CharField(max_length=10, null=True, blank=True, verbose_name="매매구분") # buy/sell
    
    quantity = models.IntegerField(default=0, verbose_name="수량")
    price = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="단가")
    amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="총 금액")
    
    is_parsed = models.BooleanField(default=False, verbose_name="파싱 성공 여부")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="수신 일시")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at.strftime('%m-%d %H:%M')}] {self.stock_name} ({self.trade_type}) - {self.amount:,.0f}원"

# 9-1. 관심 종목 (Interest Stock)
class InterestStock(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interest_stocks', verbose_name="사용자")
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='interested_users', verbose_name="종목")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'stock')
        verbose_name = "관심 종목"
        verbose_name_plural = "관심 종목 목록"

    def __str__(self):
        return f"{self.user.username} - {self.stock.name}"

import secrets

# 10. 사용자 프로필 (API Key 저장소)
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    secret_key = models.CharField(max_length=100, unique=True, blank=True, verbose_name="연동 API Key")

    def save(self, *args, **kwargs):
        if not self.secret_key:
            self.secret_key = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username}의 프로필"

# 10-1. 계좌 (Account)
class Account(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='accounts', verbose_name="소속 회사")
    financial_institution = models.CharField(max_length=50, verbose_name="금융회사명") # 예: 미래에셋, 키움
    account_number = models.CharField(max_length=50, verbose_name="계좌번호")
    account_holder = models.CharField(max_length=50, verbose_name="예금주명")
    nickname = models.CharField(max_length=50, blank=True, verbose_name="계좌별명")
    
    is_default = models.BooleanField(default=False, verbose_name="기본 계좌 여부")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_label(self):
        # Masking logic: Show first 5, last 3. Everything else *.
        # Example: 1234567890 -> 12345**890
        raw = self.account_number
        if len(raw) <= 8:
            masked = raw # Too short to mask strictly
        else:
            prefix = raw[:5]
            suffix = raw[-3:]
            # Calculate number of stars needed
            star_count = len(raw) - 8
            masked = f"{prefix}{'*' * star_count}{suffix}"
            
        return f"{self.nickname} ({masked})" if self.nickname else f"{self.financial_institution} ({masked})"

    def __str__(self):
        return f"{self.nickname} ({self.financial_institution})" if self.nickname else f"{self.financial_institution} {self.account_number}"

# 11. 회계 및 자금 트랜잭션 (Transaction)
class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('DEPOSIT', '입금'),
        ('WITHDRAW', '출금'),
        ('BUY', '매수'),
        ('SELL', '매도'),
        ('DIVIDEND', '배당'),
        ('EXPENSE', '비용/지출'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='transactions')
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name="거래 계좌") # [New]
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, verbose_name="거래 유형")
    amount = models.DecimalField(max_digits=20, decimal_places=2, verbose_name="변동 금액")
    related_asset = models.ForeignKey('Stock', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="관련 자산(종목)")
    quantity = models.IntegerField(default=0, verbose_name="수량 변동")
    price = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, verbose_name="단가")
    profit = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="실현손익 (Profit)")
    fee = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="수수료") # [K-IFRS]
    tax = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="세금")   # [K-IFRS]
    balance_after = models.DecimalField(max_digits=15, decimal_places=0, verbose_name="거래 후 잔액")
    description = models.TextField(blank=True, verbose_name="적요")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="일시")

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.get_transaction_type_display()}] {self.amount:,.0f}원 ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"

# 12. 일별 재무 스냅샷 (DailySnapshot)
class DailySnapshot(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='daily_snapshots')
    date = models.DateField(verbose_name="기준 일자")
    
    # BS (재무상태표)
    total_cash = models.DecimalField(max_digits=20, decimal_places=2, verbose_name="현금 자산")
    total_stock_value = models.DecimalField(max_digits=20, decimal_places=2, verbose_name="주식 평가액")
    total_assets = models.DecimalField(max_digits=20, decimal_places=2, verbose_name="총 자산")
    total_liabilities = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="총 부채")
    total_equity = models.DecimalField(max_digits=20, decimal_places=2, verbose_name="자본 총계")
    
    # [K-IFRS] 자본 세부 항목
    capital_stock = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="자본금")
    retained_earnings = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="이익잉여금")

    # IS (손익계산서 - 해당 일자 스냅샷 기준 누적 혹은 변동)
    realized_pl = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="누적 실현 손익")
    unrealized_pl = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="평가 손익")
    
    # [K-IFRS] 차감 항목
    total_fees = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="누적 수수료")
    total_taxes = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="누적 세금")
    
    net_income = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="당기 순이익(추정)")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} 재무보고 ({self.organization.name})"
