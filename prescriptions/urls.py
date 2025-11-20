from django.urls import path
from . import views

app_name = "prescriptions"
urlpatterns = [
    path("pharmacy/", views.pharmacy_panel, name="pharmacy_panel"),
    path("<int:pk>/dispense/", views.dispense, name="dispense"),
]
