from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout
from django.shortcuts import redirect
from core.views import index
from core.forms import CaptchaAuthenticationForm


def logout_view(request):
    logout(request)
    return redirect("/internal/")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("internal/", index, name="index"),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=CaptchaAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", logout_view, name="logout"),

    path("queues/", include("queues.urls")),
    path("prescriptions/", include("prescriptions.urls")),
    path("inventory/", include("inventory.urls")),
    path("appointments/", include("appointments.urls")),
    path(
        "patients/",    
        include(("patients.urls", "patients"), namespace="patients")
    ),
    path("", include(("public.urls", "public"), namespace="public")),

]
