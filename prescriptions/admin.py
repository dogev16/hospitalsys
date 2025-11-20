from django.contrib import admin
from .models import Prescription, PrescriptionItem

class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0

@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("date", "patient", "doctor", "status", "created_at")
    list_filter = ("date", "doctor", "status")
    search_fields = ("patient__full_name", "patient__chart_no", "doctor__full_name")
    inlines = [PrescriptionItemInline]

@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = ("prescription", "drug", "dose", "days", "qty")
    search_fields = ("prescription__patient__full_name", "drug__name")
