# config/urls.py
from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    # 관리자 페이지
    path('admin/', admin.site.urls),

    # 1. 메인 홈
    path('', views.index, name='index'),

    # 2. 메신저 (기본 화면 & 특정 AI 선택 화면)
    path('messenger/', views.messenger, name='messenger'),
    path('messenger/<int:agent_id>/', views.messenger, name='messenger'),

    # 3. 결재 관련 (작성, 목록, 상세)
    path('approval/create/', views.create_self_approval, name='create_self_approval'),
    path('approval/list/', views.approval_list, name='approval_list'),
    path('approval/detail/<int:pk>/', views.approval_detail, name='approval_detail'),

    # 4. 조직도
    path('org/', views.org_chart, name='org_chart'),
]