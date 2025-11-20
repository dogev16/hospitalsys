from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

def group_required(*group_names):
    """
    只有指定群組可以進入，否則顯示 403。
    用法：
    @group_required("RECEPTION")
    @group_required("DOCTOR", "ADMIN")
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            if user.is_superuser:
                return view_func(request, *args, **kwargs)

            if user.groups.filter(name__in=group_names).exists():
                return view_func(request, *args, **kwargs)

            return render(request, "403.html", status=403)
        return _wrapped
    return decorator
