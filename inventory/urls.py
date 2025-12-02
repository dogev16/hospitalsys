from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("drugs/", views.drug_list, name="drug_list"),
    path("drugs/new/", views.drug_create, name="drug_create"),
    path("drugs/<int:pk>/edit/", views.edit_drug, name="edit_drug"),

    # 🔥 唯一正確的庫存調整路徑
    path("drugs/<int:pk>/adjust/", views.stock_adjust, name="adjust_stock"),

    # 歷史紀錄
    path("drugs/<int:drug_id>/history/", views.stock_history_drug, name="stock_history_drug"),
    path("history/", views.stock_history, name="stock_history"),
]
