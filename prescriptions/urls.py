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

    # 3. 醫師自己看「處方歷史列表」 
    path("doctor/history/", views.doctor_prescription_list, name="doctor_prescription_list"),

    # 4. 病人端：處方歷史列表 + 詳細內容 
    path("patient/history/", views.patient_prescription_list, name="patient_history"),
    path("patient/<int:pk>/", views.patient_prescription_detail, name="patient_detail"),
    path("pharmacy/<int:pk>/dispense/", views.dispense, name="dispense"),
    path("doctor/edit/<int:pk>/", views.edit_prescription, name="edit_prescription"),

]
