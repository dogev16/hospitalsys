from django.urls import path
from . import views

app_name = "prescriptions"

urlpatterns = [
    path("pharmacy/", views.pharmacy_panel, name="pharmacy_panel"),
    path("pharmacy/<int:pk>/", views.dispense, name="dispense"),
    path("pharmacy/<int:pk>/cancel_or_return/", views.cancel_or_return_prescription, name="cancel_or_return"),

    path("ticket/<int:ticket_id>/", views.edit_for_ticket, name="edit_for_ticket"),

    path("doctor/history/", views.doctor_prescription_list, name="doctor_prescription_list"),
    path("doctor/edit/<int:pk>/", views.edit_prescription, name="edit_prescription"),

    path("patient/history/", views.patient_prescription_list, name="patient_history"),
    path("patient/<int:pk>/", views.patient_prescription_detail, name="patient_detail"),

    path("pharmacy/review/", views.pharmacy_review_list, name="pharmacy_review_list"),
    path("pharmacy/review/<int:pk>/", views.pharmacy_review_detail, name="pharmacy_review_detail"),

    path("detail/<int:pk>/", views.prescription_detail, name="prescription_detail"),

    path("pharmacy/<int:pk>/dispense/", views.dispense_confirm, name="dispense"),

    path(
        "pharmacy/<int:pk>/dispense/confirm/",
        views.dispense_confirm,
        name="dispense_confirm",
    ),
    path("print/<int:pk>/", views.prescription_print, name="prescription_print"),

    path("public-requests/", views.public_request_list, name="public_request_list"),
    path("public-requests/<int:pk>/approve/", views.public_request_approve, name="public_request_approve"),
    path("public-requests/<int:pk>/reject/", views.public_request_reject, name="public_request_reject"),

]
