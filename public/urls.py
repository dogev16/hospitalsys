from django.urls import path
from . import views

app_name = "public"

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("doctors/", views.doctor_list, name="doctor_list"),
    path("register/confirm/", views.register_confirm, name="register_confirm"),
    path("register/success/<int:pk>/", views.register_success, name="register_success"),
]
