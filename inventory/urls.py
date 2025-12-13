from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    # drugs
    path("drugs/", views.drug_list, name="drug_list"),
    path("drugs/new/", views.drug_create, name="drug_create"),
    path("drugs/<int:pk>/edit/", views.edit_drug, name="edit_drug"),
    path("drugs/<int:drug_id>/stock-in/", views.stock_in, name="stock_in"),

    # history / expiry
    path("history/", views.stock_history, name="stock_history"),
    path("expiry-dashboard/", views.expiry_dashboard, name="expiry_dashboard"),

    # batches actions
    path("batches/<int:batch_id>/quarantine/", views.batch_quarantine, name="batch_quarantine"),
    path("batches/<int:batch_id>/unquarantine/", views.batch_unquarantine, name="batch_unquarantine"),
    path("batches/<int:batch_id>/destroy/", views.batch_destroy, name="batch_destroy"),

    # quarantine list
    path("batches/quarantine/", views.quarantine_dashboard, name="quarantine_dashboard"),
    path("history/export.csv", views.stock_history_export_csv, name="stock_history_export_csv"),

]
