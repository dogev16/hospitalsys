from django.urls import path
from . import views

app_name = "appointments"

urlpatterns = [
    path("book/", views.book, name="book"),
    # 新增：病人看診紀錄
    path("history/<str:chart_no>/", views.patient_history, name="patient_history"),
    path("detail/<int:pk>/", views.appointment_detail, name="appointment_detail"),
    path("new/<int:patient_id>/", views.appointment_new_for_patient, name="new_for_patient"),
    path(
        "new-for-patient/<int:patient_id>/",
        views.appointment_new_for_patient,
        name="new_for_patient",
    ),
]
