# C:\project\hospitalsys\queues\urls.py
from django.urls import path
from . import views

app_name = "queues"

urlpatterns = [
    # 櫃台看全部號碼
    path("reception/", views.reception_panel, name="reception_panel"),

    # 櫃台叫號畫面（有「叫下一號」的那個）
    path("reception/call/", views.reception_call, name="reception_call"),

    # 醫師面板（新版本整合叫號、開始看診、完成看診）
    path("doctor/", views.doctor_panel, name="doctor_panel"),
    path("doctor/<int:pk>/<str:act>/", views.doctor_action, name="doctor_action"),

    # 大廳叫號看板
    path("board/", views.board, name="board"),
    
    path(
        "api/current_number/",
        views.api_current_number,
        name="api_current_number",
    ),
]
