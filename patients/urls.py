from django.urls import path
from . import views

# 這一行很重要，namespace 用的名字就是 "patients"
app_name = "patients"

urlpatterns = [
    # 病人列表：/patients/
    path("", views.patient_list, name="patient_list"),

    # 新增病人：/patients/create/
    path("create/", views.patient_create, name="patient_create"),

    # 病人詳細資料：/patients/1/
    path("<int:pk>/", views.patient_detail, name="patient_detail"),

    # 編輯病人：/patients/1/edit/
    path("<int:pk>/edit/", views.patient_update, name="patient_update"),
]
