from django.urls import path
from . import views

app_name = "queues"

urlpatterns = [
    path("reception/", views.reception_panel, name="reception_panel"),

    path("reception/call/", views.reception_call, name="reception_call"),

    path("doctor/", views.doctor_panel, name="doctor_panel"),
    path("doctor/<int:pk>/<str:act>/", views.doctor_action, name="doctor_action"),

    path("board/", views.board, name="board"),
    
    path(
        "api/current_number/",
        views.api_current_number,
        name="api_current_number",
    ),
]
