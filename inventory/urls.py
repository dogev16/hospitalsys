from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("drugs/", views.drug_list, name="drug_list"),
    path("new/", views.new_drug, name="new_drug"),
    path("edit/<int:pk>/", views.edit_drug, name="edit_drug"),
    path("adjust/<int:drug_id>/", views.adjust_stock_view, name="adjust_stock"),
]
