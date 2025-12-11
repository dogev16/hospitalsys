from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("drugs/", views.drug_list, name="drug_list"),
    path("drugs/new/", views.drug_create, name="drug_create"),
    path("drugs/<int:pk>/edit/", views.edit_drug, name="edit_drug"),



    # 歷史紀錄
    path("history/", views.stock_history, name="stock_history"),
    path("expiry-dashboard/", views.expiry_dashboard, name="expiry_dashboard"),
    path("drugs/<int:drug_id>/stock-in/", views.stock_in, name="stock_in"),
]
