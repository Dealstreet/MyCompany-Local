from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from django.conf import settings

class AdminAccessRestrictionMiddleware:
    """
    일반 사용자(비-Superuser)가 Django 관리자 페이지(/admin)에 접근하는 것을 차단합니다.
    SaaS 보안 요구사항 (Option 2-B)
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            if request.user.is_authenticated and not request.user.is_superuser:
                # 일반 유저는 메인 페이지로 리다이렉트
                return redirect('index')
                # 또는 403 에러 발생 시: raise PermissionDenied
            
        return self.get_response(request)
