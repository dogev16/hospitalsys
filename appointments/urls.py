from django.urls import path
from . import views

app_name = "appointments"
urlpatterns = [
    path("book/", views.book, name="book"),
]
