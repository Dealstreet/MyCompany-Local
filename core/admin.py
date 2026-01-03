from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Organization, Agent, Task, Approval, ApprovalLine, Message

# 1. 사용자 관리 (기존 설정 유지 및 강화)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('CIS 추가 정보', {'fields': ('organization', 'role')}),
    )
    list_display = ('username', 'email', 'organization', 'role', 'is_staff')
    list_filter = ('organization', 'role', 'is_staff')

# 2. 전자결재 결재 라인 인라인 설정
class ApprovalLineInline(admin.TabularInline):
    model = ApprovalLine
    extra = 1 # 기본으로 보여줄 빈 칸 개수

# 3. 전자결재 문서 관리
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ('title', 'drafter', 'status', 'created_at')
    list_filter = ('status', 'organization', 'created_at')
    search_fields = ('title', 'content')
    inlines = [ApprovalLineInline]

# 4. AI 직원(Agent) 관리 (7가지 핵심 필드 반영)
class AgentAdmin(admin.ModelAdmin):
    # 목록에서 보여줄 항목: 이름, 부서, 직급, 업무, 종목코드, 모델명 순
    list_display = ('name', 'department', 'position', 'role', 'ticker', 'model_name', 'organization')
    
    # 우측 필터 사이드바: 조직, 부서, 직급, 사용 모델별로 필터링 가능
    list_filter = ('organization', 'department', 'position', 'model_name')
    
    # 검색 기능: 이름, 부서, 업무내용, 종목코드로 검색 가능
    search_fields = ('name', 'department', 'role', 'ticker')
    
    # 상세 페이지에서 필드 배치 순서 (선택 사항)
    fieldsets = (
        ('기본 정보', {'fields': ('organization', 'name', 'department', 'position')}),
        ('담당 업무 및 분석 대상', {'fields': ('role', 'ticker')}),
        ('AI 엔진 설정', {'fields': ('model_name', 'persona')}),
    )

# 5. 기타 모델 등록
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'agent', 'creator', 'status', 'created_at')
    list_filter = ('status', 'agent')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('agent', 'user', 'role', 'created_at')
    list_filter = ('agent', 'role')

# 모델 등록 실행
admin.site.register(User, CustomUserAdmin)
admin.site.register(Organization)
admin.site.register(Agent, AgentAdmin)
admin.site.register(Approval, ApprovalAdmin)