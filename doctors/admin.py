from django.contrib import admin
from .models import Doctor, DoctorSchedule


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "room", "user")
    search_fields = ("name", "department")


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "doctor",
        "weekday",
        "session",
        "start_time",
        "end_time",
        "slot_minutes",
        "max_patients",
        "is_active",
    )
    list_filter = ("doctor", "weekday", "session", "is_active")
