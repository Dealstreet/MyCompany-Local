from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

# 1. 회사 (Organization)
class Organization(models.Model):
    name = models.CharField(max_length=100, verbose_name="회사명")
    description = models.TextField(blank=True, verbose_name="회사 설명")
    created_at = models.DateTimeField(auto_now_add=True)

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

    def __str__(self):
        return f"{self.username} ({self.employee_id if self.employee_id else 'No ID'})"

# 3. AI 직원 (Agent) - 관리 종목(Ticker) 매핑
class Agent(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='agents', verbose_name="소속 회사")
    
    name = models.CharField(max_length=50, verbose_name="이름")
    department = models.CharField(max_length=50, default='국제금융실', verbose_name="소속 부서")
    position = models.CharField(max_length=50, default='실장', verbose_name="직급")
    role = models.CharField(max_length=100, verbose_name="담당 업무")
    ticker = models.CharField(max_length=20, blank=True, null=True, verbose_name="관리 종목코드")
    persona = models.TextField(verbose_name="프롬프트(페르소나)")
    model_name = models.CharField(max_length=50, default='gpt-4o', verbose_name="사용 모델")
    profile_image = models.ImageField(upload_to='agents/', null=True, blank=True, verbose_name="프로필 이미지")

    def __str__(self):
        return f"{self.department} {self.name} {self.position} ({self.role})"

# 4. 투자 로그 (InvestmentLog) - 최종 승인 시 생성되는 실제 자산 기록
class InvestmentLog(models.Model):
    STATUS_CHOICES = [
        ('approved', '승인완료'),
        ('rejected', '반려'),
    ]

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, verbose_name="담당 AI 직원")
    stock_code = models.CharField(max_length=20, verbose_name="종목코드")
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, verbose_name="거래금액")
    quantity = models.IntegerField(verbose_name="수량") # 매수(+), 매도(-)
    
    # 평균단가 자동 계산
    avg_price = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="평균단가", null=True, blank=True)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='approved')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # 평균단가 = |거래금액 / 수량|
        if self.total_amount and self.quantity and self.quantity != 0:
            self.avg_price = abs(self.total_amount / self.quantity)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.stock_code} - {self.quantity}주 ({self.status})"

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
    temp_stock_code = models.CharField(max_length=20, null=True, blank=True, verbose_name="임시 종목코드")
    temp_total_amount = models.DecimalField(max_digits=15, decimal_places=0, null=True, blank=True, verbose_name="임시 거래금액")
    temp_quantity = models.IntegerField(null=True, blank=True, verbose_name="임시 수량")
    
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