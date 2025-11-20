from django.contrib import admin
from .models import Appointment

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("date", "time", "doctor", "patient", "status", "created_at")
    list_filter = ("date", "doctor", "status")
    search_fields = ("patient__full_name", "patient__chart_no", "doctor__full_name")
