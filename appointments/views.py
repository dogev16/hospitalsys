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
        required=False,  # ★ 讓病歷號在「載入可約時段」時可以先空著
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
                if not chart_no:
                    messages.error(request, "請先輸入病歷號再確認掛號喵。")
                    return render(request, "appointments/book.html", {"form": form, "slots": slots})
                
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

@group_required("RECEPTION")
def patient_history(request, chart_no):
    """
    根據病歷號顯示該病人的所有看診紀錄喵
    """
    # 先找到這個病人（用 chart_no）
    patient = get_object_or_404(Patient, chart_no=chart_no)

    # 抓這個病人的所有 Appointment，照日期 / 時間由新到舊排
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
    """
    從病人詳細資料頁面進來的「新增掛號」喵
    URL: /appointments/new/<patient_id>/
    """
    patient = get_object_or_404(Patient, pk=patient_id)

    slots = []    # 可約時段列表，改成 [] 比較直覺喵
    doctor = None

    if request.method == "POST":
        action = request.POST.get("action")       # "load_slots" 或 "confirm"
        form = AppointmentForm(request.POST)

        if form.is_valid():
            doctor = form.cleaned_data["doctor"]
            appt_date = form.cleaned_data["appt_date"]

            # 有選醫師 + 日期才算可用時段喵
            if doctor and appt_date:
                # ✅ 改成用跟櫃台一樣的排班邏輯
                slots = _get_available_slots(doctor, appt_date)
                # ✅ 把時段塞進 appt_time 下拉選單（跟 book() 一樣）
                _set_time_choices(form, slots)

            # 👉 只按「載入可約時段」：不存資料，只回畫面喵
            if action == "load_slots":
                if doctor and appt_date and not slots:
                    messages.warning(
                        request,
                        "此日期沒有可掛號時段，可能門診未開或額滿喵。"
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

            # 👉 下面是「確認掛號」流程喵
            appt_time_str = request.POST.get("appt_time")

            # 沒選時段就加錯誤訊息（欄位名稱是 appt_time）喵
            if not appt_time_str:
                form.add_error("appt_time", "請先選擇可約時段喵")
            else:
                # 解析時間
                try:
                    appt_time = datetime.strptime(appt_time_str, "%H:%M").time()
                except ValueError:
                    form.add_error("appt_time", "時間格式錯誤喵")
                else:
                    # 再確認一次這個時段還是可用（避免 race condition）喵
                    latest_slots = _get_available_slots(doctor, appt_date)
                    if appt_time not in latest_slots:
                        form.add_error("appt_time", "這個時段已經無法掛號，請重新載入喵")
                    else:
                        # ✅ 先建立 Appointment（掛號紀錄）喵
                        appt = Appointment.objects.create(
                            patient=patient,
                            doctor=doctor,
                            date=appt_date,
                            time=appt_time,
                            status="booked",   # 跟櫃檯 book() 一樣用小寫 booked 喵
                        )

                        # ⭐ 從 Appointment 自動產生 VisitTicket（號碼牌）喵 ⭐

                        # 1. 同一位醫師 + 同一天，找目前最大號碼，再 +1
                        next_no = (
                            VisitTicket.objects
                            .filter(doctor=doctor, date=appt_date)
                            .aggregate(Max("number"))["number__max"]
                            or 0
                        ) + 1

                        # 2. 建立新的號碼牌，預設狀態 waiting 喵
                        VisitTicket.objects.create(
                            appointment=appt,
                            date=appt_date,
                            doctor=doctor,
                            patient=patient,
                            number=next_no,
                            status="waiting",
                        )

                        # 3. 重新整理這位醫師當天的叫號順序喵
                        _renumber_visit_tickets(doctor, appt_date)

                        # ⭐ 到這裡為止，病人自己線上掛號也會直接進入叫號隊列喵 ⭐

                        messages.success(request, "掛號已建立喵！")
                        return redirect("patients:patient_detail", pk=patient.pk)

        # 表單驗證失敗或上面加了錯誤，就再渲染一次畫面喵
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

    # GET 進來：第一次打開表單喵
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
    """
    將某一筆掛號的狀態改成 BOOKED / DONE / CANCELLED 喵
    通常給櫃檯或醫師用，在掛號列表那邊按按鈕就可以改狀態喵
    """
    appt = get_object_or_404(Appointment, pk=pk)

    new_status = request.POST.get("status")

    # 合法狀態值清單（從 model 的 STATUS_CHOICES 裡抓）喵
    valid_status_values = {value for value, _ in Appointment.STATUS_CHOICES}

    if new_status not in valid_status_values:
        messages.error(request, "不合法的狀態值喵")
    else:
        appt.status = new_status
        appt.save()
        messages.success(request, "掛號狀態已更新喵！")

    # 更新完之後回到原來的頁面（patient 詳細 or 醫師清單）喵
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)

@login_required
def doctor_today_appointments(request, doctor_id):
    """
    醫師今日門診列表喵
    URL: /appointments/doctor/<doctor_id>/today/
    會列出該醫師「今天」所有掛號，依時間排序喵
    """
    doctor = get_object_or_404(Doctor, pk=doctor_id)

    # 今天日期（有吃 Django 時區設定）喵
    today = timezone.localdate()

    # 撈出這位醫師今天的所有掛號，照時間排序喵
    appointments = (
        Appointment.objects
        .filter(doctor=doctor, date=today)
        .select_related("patient")   # 預先 join 病人，template 用起來比較快喵
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

