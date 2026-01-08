from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from django.contrib import messages
from django.db import transaction

from patients.models import Patient

from .models import ClinicProfile, Announcement, PublicRegistrationRequest

from doctors.models import Doctor, DoctorLeave, DoctorSchedule
from datetime import timedelta

from appointments.models import Appointment
from django.db import IntegrityError

def home(request):
    today = timezone.localdate()
    profile = ClinicProfile.objects.first()

    announcements = (
        Announcement.objects
        .filter(show_on_homepage=True, start_date__lte=today, end_date__gte=today)
        .order_by("-is_pinned", "-start_date", "-created_at")[:5]
    )

    homepage_doctors = Doctor.objects.all().order_by("id")[:6]

    dept_qs = (
        Doctor.objects
        .exclude(department__isnull=True)
        .exclude(department__exact="")
        .values_list("department", flat=True)
        .distinct()
    )
    homepage_departments = sorted(set(dept_qs))

    return render(request, "public/home.html", {
        "profile": profile,
        "announcements": announcements,
        "today": today,
        "homepage_doctors": homepage_doctors,
        "homepage_departments": homepage_departments,
    })


@require_http_methods(["GET", "POST"])
def register(request):
    profile = ClinicProfile.objects.first()
    today = timezone.localdate()
    max_date = today + timedelta(days=30)

    dept_qs = (
        Doctor.objects
        .exclude(department__isnull=True)
        .exclude(department__exact="")
        .values_list("department", flat=True)
        .distinct()
    )
    departments = sorted(set(dept_qs))

    selected_department = (request.POST.get("department") if request.method == "POST" else request.GET.get("department"))
    selected_department = (selected_department or "").strip()

    selected_doctor_id = (request.POST.get("doctor_id") if request.method == "POST" else request.GET.get("doctor_id"))
    selected_doctor_id = (selected_doctor_id or "").strip()

    selected_date_str = (request.POST.get("date") if request.method == "POST" else request.GET.get("date"))
    selected_date_str = (selected_date_str or "").strip()

    doctors_qs = Doctor.objects.all().order_by("id")
    if selected_department:
        doctors_qs = doctors_qs.filter(department=selected_department)

    selected_date = None
    if selected_date_str:
        try:
            selected_date = timezone.datetime.fromisoformat(selected_date_str).date()
        except ValueError:
            selected_date = None

    doctor_leave_info = None
    if selected_doctor_id and selected_date:
        try:
            d = Doctor.objects.get(id=selected_doctor_id)
            leave = (
                DoctorLeave.objects
                .filter(doctor=d, is_active=True, start_date__lte=selected_date, end_date__gte=selected_date)
                .order_by("-start_date")
                .first()
            )
            if leave:
                doctor_leave_info = {
                    "start_date": leave.start_date,
                    "end_date": leave.end_date,
                    "reason": leave.reason,
                }
        except Doctor.DoesNotExist:
            pass

    time_slots = []
    slot_map = {}  # {"AM": {"slots":[...], "remaining": n}, "PM": {...}}

    if selected_doctor_id and selected_date and not doctor_leave_info:
        try:
            doctor = Doctor.objects.get(id=selected_doctor_id)
            weekday = selected_date.weekday()

            schedules = DoctorSchedule.objects.filter(
                doctor=doctor,
                weekday=weekday,
                is_active=True,
            ).order_by("session", "start_time")

            for sch in schedules:
                slots_raw = generate_time_slots(sch)

                occupied = get_occupied_count(sch, selected_date)
                remaining = max(0, sch.max_patients - occupied)

                slots = []
                for t in slots_raw:
                    appt_time = datetime.strptime(t, "%H:%M").time()
                    taken = get_occupied_count_by_time(sch, selected_date, appt_time) > 0

                    slots.append({
                        "time": t,
                        "available": not taken,
                    })

                time_slots.append({
                    "session": sch.session,
                    "session_label": sch.get_session_display(),
                    "slots": slots,
                    "remaining": remaining,
                })

                slot_map[sch.session] = {"slots": slots, "remaining": remaining}

        except Doctor.DoesNotExist:
            pass

    if request.method == "POST":
        department = selected_department
        doctor_id = selected_doctor_id
        date_str = selected_date_str

        name = (request.POST.get("name") or "").strip()
        national_id = (request.POST.get("national_id") or "").strip().upper()
        birth_date_str = (request.POST.get("birth_date") or "").strip()
        phone = (request.POST.get("phone") or "").strip()

        errors = []

        if not department:
            errors.append("請先選擇科別")
        if not doctor_id:
            errors.append("請選擇醫師")
        if not date_str:
            errors.append("請選擇日期")
        if not name:
            errors.append("請輸入姓名")
        if not national_id:
            errors.append("請輸入身分證字號")
        if not birth_date_str:
            errors.append("請輸入生日")
        if not phone:
            errors.append("請輸入聯絡電話")

        doctor_obj = None
        if doctor_id:
            try:
                doctor_obj = Doctor.objects.get(id=doctor_id)
                if department and doctor_obj.department != department:
                    errors.append("所選醫師不屬於該科別")
            except Doctor.DoesNotExist:
                errors.append("所選醫師不存在")

        appt_date = None
        if date_str:
            try:
                appt_date = timezone.datetime.fromisoformat(date_str).date()
            except ValueError:
                errors.append("日期格式不正確")

        if appt_date:
            if appt_date < today:
                errors.append("日期不可選擇過去的日期")
            if appt_date > max_date:
                errors.append("日期僅提供未來 30 天內掛號")

        birth_date = None
        if birth_date_str:
            try:
                birth_date = timezone.datetime.fromisoformat(birth_date_str).date()
            except ValueError:
                errors.append("生日格式不正確")

        if doctor_obj and appt_date:
            leave = (
                DoctorLeave.objects
                .filter(doctor=doctor_obj, is_active=True, start_date__lte=appt_date, end_date__gte=appt_date)
                .order_by("-start_date")
                .first()
            )
            if leave:
                errors.append(f"該醫師於 {leave.start_date} ～ {leave.end_date} 停診，請改選其他日期或醫師")
                doctor_leave_info = {
                    "start_date": leave.start_date,
                    "end_date": leave.end_date,
                    "reason": leave.reason,
                }

        time_value = (request.POST.get("time") or "").strip()
        period = ""
        time_str = ""
        if "|" in time_value:
            period, time_str = time_value.split("|", 1)
            period = period.strip()
            time_str = time_str.strip()
        else:
            errors.append("請選擇時間")

        if period not in {"AM", "PM"}:
            errors.append("時段不正確")

        appt_time = None
        if time_str:
            try:
                appt_time = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                errors.append("時間格式不正確")
        else:
            errors.append("請選擇時間")

        if doctor_obj and appt_date and not doctor_leave_info:
            allowed = slot_map.get(period, {}).get("slots", [])
            remaining = slot_map.get(period, {}).get("remaining", 0)

            allowed_times = {s["time"] for s in allowed if s.get("available")}
            if time_str not in allowed_times:
                errors.append("所選時間不可用，請重新選擇")

            if remaining <= 0:
                errors.append("該時段已額滿，請改選其他時間")

            sch = DoctorSchedule.objects.filter(
                doctor=doctor_obj,
                weekday=appt_date.weekday(),
                session=period,
                is_active=True,
            ).first()

            if sch and get_occupied_count_by_time(sch, appt_date, appt_time) > 0:
                errors.append("所選時間已被預約，請重新選擇")

        

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "public/register.html", {
                "profile": profile,
                "departments": departments,
                "selected_department": selected_department,
                "doctors": doctors_qs,
                "posted": request.POST,
                "min_date": str(today),
                "max_date": str(max_date),
                "selected_doctor_id": selected_doctor_id,
                "doctor_leave_info": doctor_leave_info,
                "selected_date_str": date_str,
                "time_slots": time_slots, 
            })
        
        if Appointment.objects.filter(
            doctor=doctor_obj, date=appt_date, time=appt_time
        ).exclude(status="CANCELLED").exists():
            messages.error(request, "所選時間已被預約，請重新選擇")
            return render(request, "public/register.html", {
                "profile": profile,
                "departments": departments,
                "selected_department": selected_department,
                "doctors": doctors_qs,
                "posted": request.POST,
                "min_date": str(today),
                "max_date": str(max_date),
                "selected_doctor_id": selected_doctor_id,
                "doctor_leave_info": doctor_leave_info,
                "selected_date_str": date_str,
                "time_slots": time_slots,
            })

        try:
            with transaction.atomic():
                patient, _ = Patient.objects.get_or_create(
                    national_id=national_id,
                    defaults={
                        "full_name": name,
                        "birth_date": birth_date,
                        "phone": phone,
                    }
                )

                appointment = Appointment.objects.create(
                    patient=patient,
                    doctor=doctor_obj,
                    date=appt_date,
                    time=appt_time,
                    status=Appointment.STATUS_BOOKED,
                )


                req = PublicRegistrationRequest.objects.create(
                    department=department,
                    doctor=doctor_obj,
                    date=appt_date,
                    period=period,
                    time=appt_time,
                    name=name,
                    national_id=national_id,
                    birth_date=birth_date,
                    phone=phone,
                    appointment=appointment,
                    status=PublicRegistrationRequest.STATUS_PENDING,
                )

            return redirect("public:register_success", pk=req.pk)

        except IntegrityError:
            messages.error(request, "所選時間已被預約，請重新選擇")
            return render(request, "public/register.html", {
                "profile": profile,
                "departments": departments,
                "selected_department": selected_department,
                "doctors": doctors_qs,
                "posted": request.POST,
                "min_date": str(today),
                "max_date": str(max_date),
                "selected_doctor_id": selected_doctor_id,
                "doctor_leave_info": doctor_leave_info,
                "selected_date_str": date_str,
                "time_slots": time_slots,
            })



    return render(request, "public/register.html", {
        "profile": profile,
        "departments": departments,
        "selected_department": selected_department,
        "doctors": doctors_qs,
        "posted": {},
        "min_date": str(today),
        "max_date": str(max_date),
        "selected_doctor_id": selected_doctor_id,
        "doctor_leave_info": doctor_leave_info,
        "selected_date_str": selected_date_str,
        "time_slots": time_slots,  
    })



def register_success(request, pk):
    profile = ClinicProfile.objects.first()
    req = get_object_or_404(PublicRegistrationRequest, pk=pk)

    period_label = "上午" if req.period == "AM" else "下午"

    return render(request, "public/register_success.html", {
        "profile": profile,
        "req": req,
        "period_label": period_label,
    })

def doctor_list(request):
    profile = ClinicProfile.objects.first()

    dept_qs = (
        Doctor.objects
        .exclude(department__isnull=True)
        .exclude(department__exact="")
        .values_list("department", flat=True)
        .distinct()
    )
    departments = sorted(set(dept_qs))

    selected_department = (request.GET.get("department") or "").strip()

    doctors = Doctor.objects.all().order_by("id")
    if selected_department:
        doctors = doctors.filter(department=selected_department)

    return render(request, "public/doctor_list.html", {
        "profile": profile,
        "departments": departments,
        "selected_department": selected_department,
        "doctors": doctors,
    })

@require_http_methods(["GET", "POST"])
def register_confirm(request):
    profile = ClinicProfile.objects.first()
    data = request.session.get("public_register")
    if not data:
        messages.error(request, "找不到掛號資料，請重新填寫")
        return redirect("public:register")

    if request.session.get("public_register_appt_id"):
        return redirect("public:register_success")

    doctor = Doctor.objects.get(id=data["doctor_id"])
    appt_date = timezone.datetime.fromisoformat(data["date"]).date()
    period = data["period"]

    if request.method == "GET":
        period_label = "上午" if period == "AM" else "下午"
        return render(request, "public/register_confirm.html", {
            "profile": profile,
            "data": data,
            "doctor": doctor,
            "appt_date": appt_date,
            "period_label": period_label,
        })

    leave = DoctorLeave.objects.filter(
        doctor=doctor,
        is_active=True,
        start_date__lte=appt_date,
        end_date__gte=appt_date,
    ).first()
    if leave:
        messages.error(request, f"該醫師於 {leave.start_date} ～ {leave.end_date} 停診，請改選其他日期或醫師")
        return redirect("public:register")

    with transaction.atomic():

        pass

    request.session.modified = True
    return redirect("public:register_success")

from datetime import datetime, timedelta

def generate_time_slots(schedule):

    slots = []

    start = datetime.combine(datetime.today(), schedule.start_time)
    end = datetime.combine(datetime.today(), schedule.end_time)

    cur = start
    while cur < end:
        slots.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=schedule.slot_minutes)

    return slots


def get_occupied_count(schedule, date):
    return Appointment.objects.filter(
        doctor=schedule.doctor,
        date=date,
        time__gte=schedule.start_time,
        time__lt=schedule.end_time,
    ).exclude(
        status="CANCELLED"
    ).count()


def get_occupied_count_by_time(schedule, date, appt_time):
    return Appointment.objects.filter(
        doctor=schedule.doctor,
        date=date,
        time=appt_time,
    ).exclude(
        status="CANCELLED"
    ).count()
