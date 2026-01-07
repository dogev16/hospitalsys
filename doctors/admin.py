from django.contrib import admin
from .models import Doctor, DoctorLeave, DoctorSchedule


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
    
@admin.register(DoctorLeave)
class DoctorLeaveAdmin(admin.ModelAdmin):
    list_display = ("doctor", "date_range", "is_active", "reason", "created_at")
    list_filter = ("is_active", "start_date", "end_date", "doctor")
    search_fields = (
        "doctor__user__username",
        "doctor__user__first_name",
        "doctor__user__last_name",
        "reason",
    )
    autocomplete_fields = ("doctor",)
    list_editable = ("is_active",)
    ordering = ("-start_date", "-created_at")
    date_hierarchy = "start_date"

    @admin.display(description="期間")
    def date_range(self, obj):
        if obj.start_date == obj.end_date:
            return str(obj.start_date)
        return f"{obj.start_date} ～ {obj.end_date}"