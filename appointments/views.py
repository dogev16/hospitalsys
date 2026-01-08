from datetime import datetime, timedelta, time

from django import forms
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from common.utils import group_required
from doctors.models import Doctor, DoctorSchedule
from patients.models import Patient
from .models import Appointment
from .forms import AppointmentForm

from django.db.models import Max
from queues.models import VisitTicket

from django.db import transaction

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST


# --- 掛號表單（櫃台用） ---
class AppointmentForm(forms.Form):
    chart_no = forms.CharField(
        label="病歷號",
        max_length=20,
        required=False,  
    )
    doctor = forms.ModelChoiceField(
        label="醫師",
        queryset=Doctor.objects.filter(is_active=True),
    )
    appt_date = forms.DateField(
        label="看診日期",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    appt_time = forms.TimeField(
        label="看診時段",
        required=False,
        widget=forms.Select(),
    )


def _get_available_slots(doctor, appt_date):

    weekday = appt_date.weekday()  # Monday = 0

   
    schedules = (
        DoctorSchedule.objects.filter(
            doctor=doctor,
            weekday=weekday,
            is_active=True,
        )
        .order_by("start_time")
    )
    if not schedules:
        return []

    
    taken_times = set(
        Appointment.objects.filter(
            doctor=doctor,
            date=appt_date,
        ).values_list("time", flat=True)
    )

    now = timezone.localtime()
    tz = timezone.get_current_timezone()

    slots: list[time] = []

    
    for schedule in schedules:
        start_dt = datetime.combine(appt_date, schedule.start_time)
        end_dt = datetime.combine(appt_date, schedule.end_time)

       
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, tz)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, tz)

        cursor = start_dt
        count_for_this_schedule = 0  

        while cursor <= end_dt:
            t = cursor.time()

            
            if appt_date == now.date():
                if cursor <= now + timedelta(minutes=30):
                    cursor += timedelta(minutes=schedule.slot_minutes)
                    continue

         
            if t not in taken_times:
                slots.append(t)
                count_for_this_schedule += 1

       
            if count_for_this_schedule >= schedule.max_patients:
                break

            cursor += timedelta(minutes=schedule.slot_minutes)

    
    return slots

def _renumber_visit_tickets(doctor, appt_date):

    tickets = list(
        VisitTicket.objects
        .filter(doctor=doctor, date=appt_date)
        .select_related("appointment")
        .order_by("appointment__time", "created_at", "id")
    )

    if not tickets:
        return

    with transaction.atomic():
        temp_base = 1000  

        
        for idx, t in enumerate(tickets, start=1):
            new_temp = temp_base + idx
            if t.number != new_temp:
                t.number = new_temp
                t.save(update_fields=["number"])

        
        for idx, t in enumerate(tickets, start=1):
            if t.number != idx:
                t.number = idx
                t.save(update_fields=["number"])


def _set_time_choices(form, slots):

    choices = [("", "---- 請選擇時段 ----")]
    for t in slots:
        s = t.strftime("%H:%M")
        choices.append((s, s))
    form.fields["appt_time"].widget = forms.Select(choices=choices)


@group_required("RECEPTION")
def book(request):

    slots = []

    if request.method == "POST":
        action = request.POST.get("action")
        form = AppointmentForm(request.POST)

        if form.is_valid():
            chart_no = form.cleaned_data["chart_no"]
            doctor = form.cleaned_data["doctor"]
            appt_date = form.cleaned_data["appt_date"]

            
            slots = _get_available_slots(doctor, appt_date)
            _set_time_choices(form, slots)

           
            if action == "load_slots":
                if not slots:
                    messages.warning(request, "此日期沒有可掛號時段，可能門診未開或額滿。")
                return render(request, "appointments/book.html", {"form": form, "slots": slots})

            
            if action == "confirm":
                if not chart_no:
                    messages.error(request, "請先輸入病歷號再確認掛號 。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})
                
                
                try:
                    patient = Patient.objects.get(chart_no=chart_no)
                except Patient.DoesNotExist:
                    messages.error(request, "查無此病歷號，請先建立病人資料。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})


                appt_time_str = request.POST.get("appt_time")
                if not appt_time_str:
                    messages.error(request, "請先選擇看診時段。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})

                
                try:
                    appt_time = datetime.strptime(appt_time_str, "%H:%M").time()
                except ValueError:
                    messages.error(request, "看診時段格式錯誤。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})

                
                latest_slots = _get_available_slots(doctor, appt_date)
                if appt_time not in latest_slots:
                    messages.error(request, "這個時段已經無法掛號，請重新載入時段。")
                    return render(request, "appointments/book.html", {"form": form, "slots": latest_slots})

                
                appointment = Appointment.objects.create(
                    patient=patient,
                    doctor=doctor,
                    date=appt_date,
                    time=appt_time,
                    status=Appointment.STATUS_BOOKED,
                )


                
                next_no = (
                    VisitTicket.objects
                   .filter(doctor=doctor, date=appt_date)
                   .aggregate(Max("number"))["number__max"]
                    or 0
                ) + 1


                
                VisitTicket.objects.create(
                    appointment=appointment,
                    date=appt_date,
                    doctor=doctor,
                    patient=patient,
                    number=next_no,      
                    status="WAITING",    
                )
                
                
                _renumber_visit_tickets(doctor, appt_date)


                
                messages.success(
                    request,
                    f"掛號成功：{patient} / {doctor.name} / {appt_date} {appt_time_str} 。",
                )

                return redirect("appointments:book")
        else:
            
            return render(request, "appointments/book.html", {"form": form, "slots": slots})

    else:
        
        form = AppointmentForm()

    return render(request, "appointments/book.html", {"form": form, "slots": slots})

@group_required("RECEPTION")
def patient_history(request, chart_no):

    
    patient = get_object_or_404(Patient, chart_no=chart_no)

    
    appointments = (
        Appointment.objects
        .filter(patient=patient)
        .select_related("doctor")
        .order_by("-date", "-time")
    )

    context = {
        "patient": patient,
        "appointments": appointments,
    }
    return render(request, "appointments/patient_history.html", context)

@login_required
def appointment_detail(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    return render(request, "appointments/appointment_detail.html", {"appt": appt})

@login_required
def appointment_new_for_patient(request, patient_id):

    patient = get_object_or_404(Patient, pk=patient_id)

    slots = []    
    doctor = None

    if request.method == "POST":
        action = request.POST.get("action")       
        form = AppointmentForm(request.POST)

        if form.is_valid():
            doctor = form.cleaned_data["doctor"]
            appt_date = form.cleaned_data["appt_date"]

            
            if doctor and appt_date:
                
                slots = _get_available_slots(doctor, appt_date)
                
                _set_time_choices(form, slots)

            
            if action == "load_slots":
                if doctor and appt_date and not slots:
                    messages.warning(
                        request,
                        "此日期沒有可掛號時段，可能門診未開或額滿 。"
                    )
                return render(
                    request,
                    "appointments/book_for_patient.html",
                    {
                        "form": form,
                        "slots": slots,
                        "patient": patient,
                        "doctor": doctor,
                    },
                )

            
            appt_time_str = request.POST.get("appt_time")

            
            if not appt_time_str:
                form.add_error("appt_time", "請先選擇可約時段 ")
            else:
                
                try:
                    appt_time = datetime.strptime(appt_time_str, "%H:%M").time()
                except ValueError:
                    form.add_error("appt_time", "時間格式錯誤 ")
                else:
                   
                    latest_slots = _get_available_slots(doctor, appt_date)
                    if appt_time not in latest_slots:
                        form.add_error("appt_time", "這個時段已經無法掛號，請重新載入 ")
                    else:
                     
                        appt = Appointment.objects.create(
                            patient=patient,
                            doctor=doctor,
                            date=appt_date,
                            time=appt_time,
                            status=Appointment.STATUS_BOOKED, 
                        )

                      

                        
                        next_no = (
                            VisitTicket.objects
                            .filter(doctor=doctor, date=appt_date)
                            .aggregate(Max("number"))["number__max"]
                            or 0
                        ) + 1

                       
                        VisitTicket.objects.create(
                            appointment=appt,
                            date=appt_date,
                            doctor=doctor,
                            patient=patient,
                            number=next_no,
                            status="WAITING",
                        )

                        
                        _renumber_visit_tickets(doctor, appt_date)

                        

                        messages.success(request, "掛號已建立 ！")
                        return redirect("patients:patient_detail", pk=patient.pk)

       
        return render(
            request,
            "appointments/book_for_patient.html",
            {
                "form": form,
                "slots": slots,
                "patient": patient,
                "doctor": doctor,
            },
        )

  
    else:
        form = AppointmentForm()
        return render(
            request,
            "appointments/book_for_patient.html",
            {
                "form": form,
                "slots": slots,
                "patient": patient,
                "doctor": None,
            },
        )
@login_required
@require_POST
def appointment_update_status(request, pk):

    appt = get_object_or_404(Appointment, pk=pk)

    new_status = request.POST.get("status")

   
    valid_status_values = {value for value, _ in Appointment.STATUS_CHOICES}

    if new_status not in valid_status_values:
        messages.error(request, "不合法的狀態值 ")
    else:
        appt.status = new_status
        appt.save()
        messages.success(request, "掛號狀態已更新 ！")

   
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)

@login_required
def doctor_today_appointments(request, doctor_id):

    doctor = get_object_or_404(Doctor, pk=doctor_id)

    
    today = timezone.localdate()

    
    appointments = (
        Appointment.objects
        .filter(doctor=doctor, date=today)
        .select_related("patient")   
        .order_by("time")
    )

    return render(
        request,
        "appointments/doctor_today_list.html",
        {
            "doctor": doctor,
            "appointments": appointments,
            "today": today,
        },
    )

