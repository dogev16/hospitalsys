from django.contrib import admin
from .models import Patient

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("chart_no", "full_name", "national_id", "phone")
    search_fields = ("chart_no", "full_name", "national_id")
