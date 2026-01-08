from django.contrib import admin
from django.urls import path
from django.conf import settings 
from django.conf.urls.static import static 
from django.contrib.auth import views as auth_views
from core import views
from core.views import SmsWebhookView

urlpatterns = [
    # 관리자 페이지
    path('admin/', admin.site.urls),

    # 로그인 / 로그아웃
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # 1. 메인 홈
    path('', views.index, name='index'),

    # 2. 메신저 (AI 직원 대화)
    path('messenger/', views.messenger, name='messenger'),
    path('messenger/<int:agent_id>/', views.messenger, name='messenger'),

    # 3. 투자 관리 (신규 추가: 꼼먕 투자일지 포트폴리오)
    # investment_management 함수와 연결
    path('investment/', views.investment_management, name='investment_management'),

    # 4. 결재 관련 (작성, 목록, 상세)
    # approval_detail에서 투자 로그(InvestmentLog) 연동 처리
    path('approval/create/', views.create_self_approval, name='create_self_approval'),
    path('approval/list/', views.approval_list, name='approval_list'),
    path('approval/detail/<int:pk>/', views.approval_detail, name='approval_detail'),

    # 5. 조직도
    path('org/', views.org_chart, name='org_chart'),

    # [추가] 아이폰 문자 연동 웹훅 URL
    path('api/webhook/sms/', SmsWebhookView.as_view(), name='sms_webhook'),
]

# 개발 환경(DEBUG=True)에서 미디어 및 정적 파일 서빙 설정
if settings.DEBUG:
    # Agent의 profile_image 등 미디어 파일 처리를 위해 필수
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)