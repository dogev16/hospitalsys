from django.conf import settings
from django.shortcuts import redirect

PUBLIC_PATHS = {
    "/",              # 首頁
    "/login/",
    "/logout/",
    "/admin/login/",
    "/admin/logout/",
}

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        static_url = getattr(settings, "STATIC_URL", "/static/")
        if static_url and path.startswith(static_url):
            return self.get_response(request)

        if path.startswith("/admin/"):
            return self.get_response(request)

        if path in PUBLIC_PATHS:
            return self.get_response(request)

        if request.user.is_authenticated:
            return self.get_response(request)

        login_url = settings.LOGIN_URL
        return redirect(f"{login_url}?next={path}")
