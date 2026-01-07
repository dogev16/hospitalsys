from django.urls import path
from . import views

app_name = "prescriptions"

urlpatterns = [
    # 1. 藥局端面板 + 領藥 
    path("pharmacy/", views.pharmacy_panel, name="pharmacy_panel"),
    path("pharmacy/<int:pk>/", views.dispense, name="dispense"),
    path("pharmacy/<int:pk>/cancel_or_return/", views.cancel_or_return_prescription, name="cancel_or_return"),

    # 2. 醫師在「候診列表」點進去開 / 編輯處方 
    path("ticket/<int:ticket_id>/", views.edit_for_ticket, name="edit_for_ticket"),

    # 3. 醫師查看處方歷史
    path("doctor/history/", views.doctor_prescription_list, name="doctor_prescription_list"),
    path("doctor/edit/<int:pk>/", views.edit_prescription, name="edit_prescription"),

    # 4. 病人查看處方
    path("patient/history/", views.patient_prescription_list, name="patient_history"),
    path("patient/<int:pk>/", views.patient_prescription_detail, name="patient_detail"),

    # 5. 藥師審核
    path("pharmacy/review/", views.pharmacy_review_list, name="pharmacy_review_list"),
    path("pharmacy/review/<int:pk>/", views.pharmacy_review_detail, name="pharmacy_review_detail"),

    # ⭐ 6. 通用處方詳細內容頁（你的 logs 都在這裡）
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
