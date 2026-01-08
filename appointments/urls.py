from django.urls import path
from . import views
                                                                                                                
app_name = "appointments"

urlpatterns = [
    path("book/", views.book, name="book"),
    path("history/<str:chart_no>/", views.patient_history, name="patient_history"),
    path("detail/<int:pk>/", views.appointment_detail, name="appointment_detail"),
    path("new/<int:patient_id>/", views.appointment_new_for_patient, name="new_for_patient"),
    path(
        "new-for-patient/<int:patient_id>/",
        views.appointment_new_for_patient,
        name="new_for_patient",
    ),
    path(
        "<int:pk>/status/",
        views.appointment_update_status,
        name="appointment_update_status",
    ),
    path(
        "doctor/<int:doctor_id>/today/",
        views.doctor_today_appointments,
        name="doctor_today_appointments",
    ),

]
