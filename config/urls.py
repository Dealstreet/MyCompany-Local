# config/urls.py
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views  # <--- 이 줄이 반드시 필요합니다!
from core import views

urlpatterns = [
    # 관리자 페이지
    path('admin/', admin.site.urls),

    # 로그인 / 로그아웃 (추가된 부분)
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # 1. 메인 홈
    path('', views.index, name='index'),

    # 2. 메신저
    path('messenger/', views.messenger, name='messenger'),
    path('messenger/<int:agent_id>/', views.messenger, name='messenger'),

    # 3. 결재 관련 (작성, 목록, 상세)
    path('approval/create/', views.create_self_approval, name='create_self_approval'),
    path('approval/list/', views.approval_list, name='approval_list'),
    path('approval/detail/<int:pk>/', views.approval_detail, name='approval_detail'),

    # 4. 조직도
    path('org/', views.org_chart, name='org_chart'),
]