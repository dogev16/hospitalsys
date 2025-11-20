from datetime import datetime, timedelta, time

from django import forms
from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils import timezone

from common.utils import group_required
from doctors.models import Doctor, DoctorSchedule
from patients.models import Patient
from .models import Appointment

from django.db.models import Max
from queues.models import VisitTicket

from django.db import transaction



# --- 掛號表單（櫃台用） ---
class AppointmentForm(forms.Form):
    chart_no = forms.CharField(label="病歷號", max_length=20)
    doctor = forms.ModelChoiceField(
        label="醫師",
        queryset=Doctor.objects.filter(is_active=True),
    )
    appt_date = forms.DateField(
        label="看診日期",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # 時段一開始先不給 choices，按「載入可約時段」後再塞進去
    appt_time = forms.TimeField(
        label="看診時段",
        required=False,
        widget=forms.Select(),
    )


def _get_available_slots(doctor, appt_date):
    """
    依據 DoctorSchedule + 已存在的 Appointment 計算可掛號時段列表（回傳 list[datetime.time]）
    支援同一位醫師、同一星期幾有多筆排班（早上、下午各一段）。
    """
    weekday = appt_date.weekday()  # Monday = 0

    # 🔹 一次抓出當天所有排班（可能早上 + 下午）
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

    # 已經被掛走的時段
    taken_times = set(
        Appointment.objects.filter(
            doctor=doctor,
            date=appt_date,
        ).values_list("time", flat=True)
    )

    now = timezone.localtime()
    tz = timezone.get_current_timezone()

    slots: list[time] = []

    # 🔹 逐一處理每一段排班（早上、下午各跑一次）
    for schedule in schedules:
        start_dt = datetime.combine(appt_date, schedule.start_time)
        end_dt = datetime.combine(appt_date, schedule.end_time)

        # 避免 naive / aware 混用
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, tz)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, tz)

        cursor = start_dt
        count_for_this_schedule = 0  # 每一段自己有 max_patients 限制

        while cursor <= end_dt:
            t = cursor.time()

            # 如果是今天，就略過太接近現在的時段（例如 30 分鐘內）
            if appt_date == now.date():
                if cursor <= now + timedelta(minutes=30):
                    cursor += timedelta(minutes=schedule.slot_minutes)
                    continue

            # 沒被掛走的才算可選
            if t not in taken_times:
                slots.append(t)
                count_for_this_schedule += 1

            # 這一段排班最多只開到 max_patients 個
            if count_for_this_schedule >= schedule.max_patients:
                break

            cursor += timedelta(minutes=schedule.slot_minutes)

    # slots 本身已按 start_time + 時間順序跑出來，直接回傳即可
    return slots

def _renumber_visit_tickets(doctor, appt_date):
    """
    依『醫師 + 日期』重新整理叫號順序喵：
    - 先照 appointment.time 排序
    - 再照 created_at / id 做次排序
    - 分兩階段改 number，避免 UNIQUE 衝突 meow
    """
    tickets = list(
        VisitTicket.objects
        .filter(doctor=doctor, date=appt_date)
        .select_related("appointment")
        .order_by("appointment__time", "created_at", "id")
    )

    if not tickets:
        return

    with transaction.atomic():
        temp_base = 1000  # 暫時的安全區間喵

        # 第 1 階段：先全部搬到 1001,1002,...，避開現在的號碼
        for idx, t in enumerate(tickets, start=1):
            new_temp = temp_base + idx
            if t.number != new_temp:
                t.number = new_temp
                t.save(update_fields=["number"])

        # 第 2 階段：再改回 1,2,3,... 真正要給醫生叫的號碼喵
        for idx, t in enumerate(tickets, start=1):
            if t.number != idx:
                t.number = idx
                t.save(update_fields=["number"])


def _set_time_choices(form, slots):
    """
    把可選時段塞進 appt_time 的 Select 裡
    """
    choices = [("", "---- 請選擇時段 ----")]
    for t in slots:
        s = t.strftime("%H:%M")
        choices.append((s, s))
    form.fields["appt_time"].widget = forms.Select(choices=choices)


@group_required("RECEPTION")
def book(request):
    """
    掛號畫面（櫃檯用）：
    1. 輸入病歷號 + 醫師 + 日期
    2. 按「載入可約時段」載入該日可掛號時段
    3. 選擇時段後按「確認掛號」建立 Appointment
    """
    slots = []

    if request.method == "POST":
        action = request.POST.get("action")
        form = AppointmentForm(request.POST)

        if form.is_valid():
            chart_no = form.cleaned_data["chart_no"]
            doctor = form.cleaned_data["doctor"]
            appt_date = form.cleaned_data["appt_date"]

            # 先計算這個醫師在該日期有哪些可約時段
            slots = _get_available_slots(doctor, appt_date)
            _set_time_choices(form, slots)

            # 如果只是載入時段，就直接回傳畫面
            if action == "load_slots":
                if not slots:
                    messages.warning(request, "此日期沒有可掛號時段，可能門診未開或額滿。")
                return render(request, "appointments/book.html", {"form": form, "slots": slots})

            # action == "confirm"：確認掛號
            if action == "confirm":
                # 先找病人
                try:
                    patient = Patient.objects.get(chart_no=chart_no)
                except Patient.DoesNotExist:
                    messages.error(request, "查無此病歷號，請先建立病人資料。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})

                appt_time_str = request.POST.get("appt_time")
                if not appt_time_str:
                    messages.error(request, "請先選擇看診時段。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})

                # 字串轉 time 物件
                try:
                    appt_time = datetime.strptime(appt_time_str, "%H:%M").time()
                except ValueError:
                    messages.error(request, "看診時段格式錯誤。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})

                # 再次確認這個時段還是可用（避免 race condition）
                latest_slots = _get_available_slots(doctor, appt_date)
                if appt_time not in latest_slots:
                    messages.error(request, "這個時段已經無法掛號，請重新載入時段。")
                    return render(request, "appointments/book.html", {"form": form, "slots": latest_slots})

                # 建立掛號
                appointment = Appointment.objects.create(
                    patient=patient,
                    doctor=doctor,
                    date=appt_date,
                    time=appt_time,
                    status="booked",
                )

                # 正確取得叫號序號（限定同醫師＋同日）
                next_no = (
                    VisitTicket.objects
                   .filter(doctor=doctor, date=appt_date)
                   .aggregate(Max("number"))["number__max"]
                    or 0
                ) + 1


                # 建立 VisitTicket
                VisitTicket.objects.create(
                    appointment=appointment,
                    date=appt_date,
                    doctor=doctor,
                    patient=patient,
                    number=next_no,      # 原本的 queue_no 改成 number
                    status="waiting",    # 或用你 model 的預設值也可以
                )
                
                # ★ 每次新增完 ticket 就重排一次號碼
                _renumber_visit_tickets(doctor, appt_date)


# 顯示成功訊息（修正 patient.name）
                messages.success(
                    request,
                    f"掛號成功：{patient} / {doctor.name} / {appt_date} {appt_time_str} 。",
                )

                return redirect("appointments:book")
        else:
            # form 無效，直接回傳（錯誤會顯示在欄位旁）
            return render(request, "appointments/book.html", {"form": form, "slots": slots})

    else:
        # GET：第一次進來
        form = AppointmentForm()

    return render(request, "appointments/book.html", {"form": form, "slots": slots})
