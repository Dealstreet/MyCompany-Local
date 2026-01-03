from django.db import models
from django.contrib.auth.models import AbstractUser

# 1. 회사 (Organization)
class Organization(models.Model):
    name = models.CharField(max_length=100, verbose_name="회사명")
    description = models.TextField(blank=True, verbose_name="회사 설명")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# 2. 사람 (User)
class User(AbstractUser):
    ROLE_CHOICES = [('ceo', '사장'), ('staff', '직원')]
    
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, verbose_name="소속 회사")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff', verbose_name="직책")

    groups = models.ManyToManyField(
        'auth.Group', related_name='core_user_set', blank=True,
        help_text='The groups this user belongs to.', verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', related_name='core_user_set', blank=True,
        help_text='Specific permissions for this user.', verbose_name='user permissions',
    )

# 3. AI 직원 (Agent) - [수정] ticker 필드 추가
class Agent(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='agents')
    name = models.CharField(max_length=50, verbose_name="AI 이름")
    department = models.CharField(max_length=50, default='국제금융실', verbose_name="소속 부서")
    role = models.CharField(max_length=100, verbose_name="담당 업무")
    ticker = models.CharField(max_length=10, blank=True, null=True, verbose_name="관리 종목코드(예: SPY)")
    persona = models.TextField(verbose_name="프롬프트(페르소나)")
    model_name = models.CharField(max_length=50, default='gpt-4o', verbose_name="사용 모델")
    
    def __str__(self):
        return f"{self.name} ({self.role})"

# 4. 업무 (Task)
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

# 5. 전자결재 문서 (Approval)
class Approval(models.Model):
    STATUS_CHOICES = [
        ('draft', '임시저장 (AI 작성중)'), 
        ('pending', '결재대기 (검토필요)'),
        ('approved', '최종승인'),
        ('rejected', '반려됨'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    drafter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='drafted_approvals', verbose_name="사람 기안자")
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name='drafted_approvals', verbose_name="AI 기안자")
    
    title = models.CharField(max_length=200, verbose_name="문서 제목")
    content = models.TextField(verbose_name="문서 내용") # HTML 포함
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="문서 상태")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# 6. 결재 라인 (ApprovalLine)
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

# 7. 메신저 대화 기록 (Message)
class Message(models.Model):
    ROLE_CHOICES = [('user', '사장님'), ('assistant', 'AI 직원')]

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(verbose_name="내용")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']