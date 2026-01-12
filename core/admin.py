from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Organization, Agent, Task, Approval, ApprovalLine, Message, Stock, UserProfile, InvestmentLog, Department, Transaction

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'secret_key')

@admin.register(InvestmentLog)
class InvestmentLogAdmin(admin.ModelAdmin):
    list_display = ('source', 'stock_name', 'quantity', 'status', 'approved_at', 'agent', 'user')
    list_filter = ('source', 'status', 'agent', 'user')

# 1. 사용자 관리 (기존 설정 유지)
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'transaction_type', 'amount', 'profit', 'related_asset', 'organization')
    list_filter = ('transaction_type', 'organization', 'timestamp')
    search_fields = ('description', 'related_asset__name')
    ordering = ('-timestamp',)

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
@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    # 목록에서 보여줄 항목: 사진 필드(profile_image)를 추가했습니다.
    list_display = ('name', 'department_obj', 'position', 'role', 'stock', 'model_name')
    
    # 우측 필터 사이드바
    list_filter = ('organization', 'department_obj', 'position', 'model_name')
    
    # 검색 기능
    search_fields = ('name', 'department_obj__name', 'role')

    # 자동 완성 필드 (ForeignKey 검색용)
    autocomplete_fields = ['stock']
    
    # 상세 페이지 설정: '기본 정보' 섹션에 'profile_image'를 추가하여 사진 업로드가 가능하게 했습니다.
    fieldsets = (
        ('기본 정보', {'fields': ('organization', 'name', 'department_obj', 'position', 'profile_image')}),
        ('담당 업무 및 분석 대상', {'fields': ('role', 'stock')}),
        ('AI 엔진 설정', {'fields': ('model_name', 'persona')}),
    )

    class Media:
        js = ('admin/js/agent_admin.js',)

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

admin.site.register(Approval, ApprovalAdmin)

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'get_current_price', 'get_high_52w', 'get_low_52w', 'updated_at')
    search_fields = ('name', 'code')
    actions = ['update_stock_data']

    def _format_price(self, obj, value):
        if value is None:
            return '-'
        # 한국 주식 코드(숫자 6자리)인 경우 정수 표시
        if obj.code.isdigit():
            return f"{value:,.0f}"
        # 그 외(미국 주식 등)는 소수점 2자리 표시
        return f"{value:,.2f}"

    @admin.display(description='현재가')
    def get_current_price(self, obj):
        return self._format_price(obj, obj.current_price)

    @admin.display(description='52주 고가')
    def get_high_52w(self, obj):
        return self._format_price(obj, obj.high_52w)

    @admin.display(description='52주 저가')
    def get_low_52w(self, obj):
        return self._format_price(obj, obj.low_52w)

    @admin.action(description='선택한 종목의 주가 및 캔들 데이터 업데이트')
    def update_stock_data(self, request, queryset):
        from . import utils
        success_count = 0
        fail_count = 0
        
        for stock in queryset:
            if utils.update_stock(stock):
                success_count += 1
            else:
                fail_count += 1
        
        self.message_user(
            request, 
            f"{success_count}개 종목 업데이트 성공, {fail_count}개 실패.", 
        )

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'organization')
    list_filter = ('organization', 'parent')

