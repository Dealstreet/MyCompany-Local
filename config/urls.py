from django.contrib import admin
from django.urls import path
from django.conf import settings 
from django.conf.urls.static import static 
from django.contrib.auth import views as auth_views
from core import views, views_backtest
from core.views import SmsWebhookView

urlpatterns = [
    # 관리자 페이지
    path('admin/', admin.site.urls),

    # 로그인 / 로그아웃
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('my-info/', views.my_info, name='my_info'), # [New]

    # 9. 조직 관리 (직원 관리 + 조직도)
    path('organization/agents/', views.agent_management, name='agent_management'),
    path('organization/agents/create/', views.agent_create, name='agent_create'),
    path('organization/agents/<int:pk>/edit/', views.agent_edit, name='agent_edit'),
    path('organization/agents/<int:pk>/delete/', views.agent_delete, name='agent_delete'),
    
    # 10. 즐겨찾기 API
    path('favorites/add/', views.add_favorite, name='add_favorite'),
    path('favorites/delete/<int:pk>/', views.delete_favorite, name='delete_favorite'),
    path('favorites/reorder/', views.update_favorite_order, name='update_favorite_order'),

    # 11. 마스터 대시보드
    path('master/users/', views.master_user_list, name='master_user_list'),
    path('master/users/<int:pk>/toggle/', views.master_user_toggle_status, name='master_user_toggle_status'),

    # 12. 커뮤니티
    path('community/', views.post_list, name='post_list'),
    path('community/create/', views.post_create, name='post_create'),
    path('community/<int:pk>/', views.post_detail, name='post_detail'),
    path('community/<int:pk>/edit/', views.post_edit, name='post_edit'),
    path('community/<int:pk>/delete/', views.post_delete, name='post_delete'),
    path('community/ranking/', views.portfolio_ranking, name='portfolio_ranking'),


    # 1. 메인 홈
    path('', views.index, name='index'),

    # 2. 메신저 (AI 직원 대화)
    path('messenger/', views.messenger, name='messenger'),
    path('messenger/<int:agent_id>/', views.messenger, name='messenger'),

    # 3. 투자 관리 (신규 추가: 꼼먕 투자일지 포트폴리오)
    # investment_management 함수와 연결
    path('investment/', views.investment_management, name='investment_management'),
    
    # 3-1. 재무 관리
    path('finance/', views.financial_management, name='financial_management'),
    path('finance/cash-op/', views.cash_operation, name='cash_operation'),

    # 3-2. 계좌 관리
    path('account/', views.account_management, name='account_management'),

    # 4. 결재 관련 (작성, 목록, 상세)
    # approval_detail에서 투자 로그(InvestmentLog) 연동 처리

    path('approval/list/', views.approval_list, name='approval_list'),
    path('approval/create/', views.create_self_approval, name='create_self_approval'),
    path('approval/delete-chat/<int:pk>/', views.delete_chat_room, name='delete_chat_room'), # [New]
    path('approval/detail/<int:pk>/', views.approval_detail, name='approval_detail'),
    path('approval/delete/<int:pk>/', views.delete_approval, name='delete_approval'), # [New]

    # 5. 조직도
    path('org/', views.org_chart, name='org_chart'),

    # [추가] 아이폰 문자 연동 웹훅 URL
    # [추가] 아이폰 문자 연동 웹훅 URL
    path('api/webhook/sms/', SmsWebhookView.as_view(), name='sms_webhook'),

    # [New] Stock Management
    path('stock/', views.stock_management, name='stock_management'),
    path('stock/add/', views.add_interest_stock, name='add_interest_stock'),
    path('stock/delete/<int:stock_id>/', views.delete_interest_stock, name='delete_interest_stock'),
    path('stock/detail/', views.get_stock_detail, name='get_stock_detail'),
    path('stock/search/', views.search_stock_api, name='search_stock_api'),
    path('stock/update-order/', views.update_stock_ordering, name='update_stock_ordering'),

    # [New] Trade Notifications
    path('notifications/', views.trade_notification_list, name='trade_notification_list'),
    
    # Stock APIs
    path('api/stock/update/', views.update_all_stocks_api, name='update_all_stocks_api'),

    # [New] Backtest
    path('backtest/', views_backtest.backtest_dashboard, name='backtest_dashboard'),
    path('core/backtest/run/', views_backtest.run_backtest_api, name='run_backtest_api'),
    path('core/backtest/export/', views_backtest.export_backtest_csv, name='export_backtest_csv'),

    # 13. 소셜 (피드 & 팔로우) [New]
    path('community/feed/', views.feed, name='feed'),
    path('community/follow/<int:user_id>/', views.follow_toggle, name='follow_toggle'),
]

# 개발 환경(DEBUG=True)에서 미디어 및 정적 파일 서빙 설정
if settings.DEBUG:
    # Agent의 profile_image 등 미디어 파일 처리를 위해 필수
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)