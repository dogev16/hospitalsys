from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout
from django.shortcuts import redirect
from core.views import index
from queues import views


def logout_view(request):
    logout(request)
    return redirect("/")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", index, name="index"),

    path("login/", auth_views.LoginView.as_view(
        template_name="registration/login.html"
    ), name="login"),
    path("logout/", logout_view, name="logout"),

    path("queues/", include("queues.urls")),
    path("prescriptions/", include("prescriptions.urls")),
    path("inventory/", include("inventory.urls")),
    path("appointments/", include("appointments.urls")),
    path("patients/", include(("patients.urls", "patients"), namespace="patients")),

    
    path("reception/", views.reception_panel, name="reception_panel"),
    path("doctor/", views.doctor_panel, name="doctor_panel"),
    path("doctor/<int:pk>/<str:act>/", views.doctor_action, name="doctor_action"),
    path("board/", views.board, name="board"),


]
