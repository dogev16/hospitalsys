from django.urls import path
from . import views

app_name = "inventory"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("new/", views.new_drug, name="new_drug"),
]
