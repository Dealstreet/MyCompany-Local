#config/urls.py
from django.contrib import admin
from django.urls import path
from django.conf import settings # 추가: 프로젝트 설정을 가져오기 위함
from django.conf.urls.static import static # 추가: 정적/미디어 파일 서빙용
from django.contrib.auth import views as auth_views
from core import views

urlpatterns = [
    # 관리자 페이지
    path('admin/', admin.site.urls),

    # 로그인 / 로그아웃
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

# ▼▼▼ [중요] 개발 환경에서 미디어/정적 파일을 서빙하기 위한 설정 추가 ▼▼▼
if settings.DEBUG:
    # 프로필 이미지 등 미디어 파일 설정
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # CSS, JS 등 정적 파일 설정
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)