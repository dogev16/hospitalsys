# public/admin.py
from datetime import datetime, time as pytime, timedelta

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.db import IntegrityError, transaction
from django.contrib import messages

from doctors.models import DoctorLeave, DoctorSchedule

from .models import ClinicProfile, Announcement, PublicRegistrationRequest
from patients.models import Patient
from appointments.models import Appointment
from .models import PublicRegistrationRequest


@admin.register(ClinicProfile)
class ClinicProfileAdmin(admin.ModelAdmin):
    list_display = ("name_display", "phone", "address", "updated_at")
    readonly_fields = ("updated_at",)
    search_fields = ("name", "phone", "address")
    fieldsets = (
        ("基本資訊", {"fields": ("name", "description")}),
        ("聯絡方式", {"fields": ("phone", "address", "map_url")}),
        ("門診時間", {"fields": ("opening_hours",)}),
        ("系統欄位", {"fields": ("updated_at",)}),
    )

    def name_display(self, obj):
        return obj.name or "（尚未命名）"
    name_display.short_description = "醫院名稱"

    def has_add_permission(self, request):
        if ClinicProfile.objects.exists():
            return False
        return super().has_add_permission(request)



@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "level",
        "date_range",
        "is_pinned",
        "show_on_homepage",
        "active_badge",
        "created_at",
    )
    list_filter = ("level", "is_pinned", "show_on_homepage")
    search_fields = ("title", "content")
    ordering = ("-is_pinned", "-start_date", "-created_at")
    date_hierarchy = "start_date"

    fieldsets = (
        ("公告內容", {"fields": ("title", "content")}),
        ("顯示設定", {"fields": ("level", "is_pinned", "show_on_homepage")}),
        ("有效期間", {"fields": ("start_date", "end_date")}),
    )

    @admin.display(description="期間")
    def date_range(self, obj):
        return f"{obj.start_date} ～ {obj.end_date}"

    @admin.display(description="狀態")
    def active_badge(self, obj):
        today = timezone.localdate()
        active = obj.start_date <= today <= obj.end_date
        if active:
            return format_html('<span style="color: #0a7;">有效</span>')
        return format_html('<span style="color: #999;">已過期/未開始</span>')
    
def _pick_first_slot_time(doctor, appt_date, period: str):

    weekday = appt_date.weekday()  # Mon=0
    schedules = DoctorSchedule.objects.filter(doctor=doctor, weekday=weekday).order_by("start_time")

    if not schedules.exists():
        raise ValueError("該日期無排班")

    if period == "AM":
        win_start, win_end = pytime(0, 0), pytime(12, 0)
    else:
        win_start, win_end = pytime(12, 0), pytime(23, 59, 59)

    best = None

    for s in schedules:
        start = max(s.start_time, win_start)
        end = min(s.end_time, win_end)

        if start >= end:
            continue

        base = datetime.combine(appt_date, s.start_time)
        cur = datetime.combine(appt_date, start)

        delta_min = int((cur - base).total_seconds() // 60)
        mod = delta_min % s.slot_minutes
        if mod != 0:
            cur += timedelta(minutes=(s.slot_minutes - mod))

        candidate_time = cur.time()
        if candidate_time < end:
            if best is None or candidate_time < best:
                best = candidate_time

    if best is None:
        raise ValueError("該時段沒有可掛的時間點（AM/PM 都可能被排班切掉）")

    return best

@admin.register(PublicRegistrationRequest)
class PublicRegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "doctor", "date", "period_display", "status")
    list_filter = ("status", "date", "doctor", "period")
    search_fields = ("name", "national_id", "phone")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "reviewed_at", "status")

    actions = ["approve_requests", "reject_requests"]

    @admin.display(description="時段")
    def period_display(self, obj):
        return obj.get_period_display()

    @admin.action(description="核准並建立正式掛號")
    def approve_requests(self, request, queryset):
        qs = queryset.filter(
            status=PublicRegistrationRequest.STATUS_PENDING
        ).select_related("doctor")

        if not qs.exists():
            self.message_user(request, "沒有待審核的申請 ", level=messages.WARNING)
            return

        created = 0
        skipped = 0
        failed = 0

        for req in qs:
            try:
                with transaction.atomic():
                    if DoctorLeave.objects.filter(
                        doctor=req.doctor,
                        is_active=True,
                        start_date__lte=req.date,
                        end_date__gte=req.date,
                    ).exists():
                        skipped += 1
                        self.message_user(
                            request,
                            f"停診期間：{req.name} / {req.doctor} / {req.date}  ",
                            level=messages.WARNING,
                        )
                        continue

                    patient, _ = Patient.objects.get_or_create(
                        national_id=req.national_id,
                        defaults={
                            "name": req.name,
                            "birth_date": req.birth_date,
                            "phone": req.phone,
                        }
                    )


                    appt_time = req.time
                    if not appt_time:
                        skipped += 1
                        self.message_user(
                            request,
                            f"申請單沒有時間：{req.name} / {req.doctor} / {req.date}  ",
                            level=messages.WARNING,
                        )
                        continue

                    if Appointment.objects.filter(
                        doctor=req.doctor,
                        date=req.date,
                        time=appt_time,
                    ).exists():
                        skipped += 1
                        self.message_user(
                            request,
                            f"時段已滿：{req.doctor} / {req.date} {appt_time}（{req.name}） ",
                            level=messages.WARNING,
                        )
                        continue

                    appointment = Appointment.objects.create(
                        patient=patient,
                        doctor=req.doctor,
                        date=req.date,
                        time=appt_time,
                    )


                    req.status = PublicRegistrationRequest.STATUS_APPROVED
                    req.reviewed_at = timezone.now()
                    req.save(update_fields=["status", "reviewed_at"])

                    created += 1

            except Exception as e:
                failed += 1
                self.message_user(
                    request,
                    f"建立失敗：{req.name} / {req.doctor} / {req.date}（{e}） ",
                    level=messages.ERROR,
                )

        self.message_user(
            request,
            f"已成功建立 {created} 筆；跳過 {skipped} 筆；失敗 {failed} 筆 ",
            level=messages.SUCCESS if failed == 0 else messages.WARNING,
        )

    @admin.action(description="駁回申請（標記為駁回）")
    def reject_requests(self, request, queryset):
        qs = queryset.filter(status=PublicRegistrationRequest.STATUS_PENDING)
        updated = qs.update(
            status=PublicRegistrationRequest.STATUS_REJECTED,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"已駁回 {updated} 筆 ", level=messages.SUCCESS)


    

