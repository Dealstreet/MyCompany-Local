from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Organization, Agent, Task, Approval, ApprovalLine, Message

# 1. 사용자 관리 (기존 설정 유지)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('CIS 추가 정보', {'fields': ('organization', 'role')}),
    )
    list_display = ('username', 'email', 'organization', 'role', 'is_staff')
    list_filter = ('organization', 'role', 'is_staff')

# 2. 전자결재 결재 라인 인라인 설정
class ApprovalLineInline(admin.TabularInline):
    model = ApprovalLine
    extra = 1

# 3. 전자결재 문서 관리
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ('title', 'drafter', 'status', 'created_at')
    list_filter = ('status', 'organization', 'created_at')
    search_fields = ('title', 'content')
    inlines = [ApprovalLineInline]

# 4. AI 직원(Agent) 관리 - [수정] profile_image 필드 추가
class AgentAdmin(admin.ModelAdmin):
    # 목록에서 보여줄 항목: 사진 필드(profile_image)를 추가했습니다.
    list_display = ('name', 'department', 'position', 'role', 'ticker', 'model_name', 'organization', 'profile_image')
    
    # 우측 필터 사이드바
    list_filter = ('organization', 'department', 'position', 'model_name')
    
    # 검색 기능
    search_fields = ('name', 'department', 'role', 'ticker')
    
    # 상세 페이지 설정: '기본 정보' 섹션에 'profile_image'를 추가하여 사진 업로드가 가능하게 했습니다.
    fieldsets = (
        ('기본 정보', {'fields': ('organization', 'name', 'department', 'position', 'profile_image')}),
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