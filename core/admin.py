from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Organization, Agent, Task, Approval, ApprovalLine

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('CIS 추가 정보', {'fields': ('organization', 'role')}),
    )
    list_display = ('username', 'email', 'organization', 'role', 'is_staff')

class ApprovalLineInline(admin.TabularInline):
    model = ApprovalLine
    extra = 1

class ApprovalAdmin(admin.ModelAdmin):
    list_display = ('title', 'drafter', 'status', 'created_at')
    inlines = [ApprovalLineInline]

# [수정] Agent 목록에 ticker 표시
class AgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'role', 'ticker', 'model_name')

admin.site.register(User, CustomUserAdmin)
admin.site.register(Organization)
admin.site.register(Agent, AgentAdmin)
admin.site.register(Task)
admin.site.register(Approval, ApprovalAdmin)