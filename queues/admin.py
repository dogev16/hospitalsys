from django.contrib import admin
from .models import VisitTicket

@admin.register(VisitTicket)
class VisitTicketAdmin(admin.ModelAdmin):
    list_display = ("date", "doctor", "number", "patient", "status", "called_at", "finished_at")
    list_filter = ("date", "doctor", "status")
    search_fields = ("patient__full_name", "patient__chart_no", "doctor__full_name")
    ordering = ("-date", "doctor", "number")
