from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test

def group_required(group_name):
    def decorator(view_func):
        decorated_view_func = user_passes_test(
            lambda u: u.is_authenticated and u.groups.filter(name=group_name).exists()
        )(view_func)
        return decorated_view_func
    return decorator


