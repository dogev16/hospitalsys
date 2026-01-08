from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from common.utils import group_required
from .models import VisitTicket
from doctors.models import Doctor, DoctorSchedule
from django.db.models import F
from django.db import transaction

from django.contrib import messages

from datetime import datetime
from django.urls import reverse
from django.contrib import messages
from appointments.models import Appointment
from prescriptions.models import Prescription


@group_required("RECEPTION")
def reception_panel(request):
    today = timezone.localdate()
    tickets = VisitTicket.objects.filter(date=today).order_by("doctor__name", "number")
    return render(request, "queues/reception.html", {"tickets": tickets})


@group_required("RECEPTION")
def reception_call(request):
    today = timezone.localdate()
    doctors = Doctor.objects.all().order_by("name")

    # 先看看有沒有 doctor 參數 
    doctor_id = request.GET.get("doctor") or request.POST.get("doctor")
    selected_doctor = None
    tickets_qs = VisitTicket.objects.none()
    current_ticket = None

    # 沒選就預設第一位醫師 
    if not doctor_id and doctors.exists():
        selected_doctor = doctors.first()
        doctor_id = selected_doctor.id
    elif doctor_id:
        selected_doctor = get_object_or_404(Doctor, pk=doctor_id)

    # 讀取目前醫師的叫號資料 
    if selected_doctor:
        tickets_qs = (
            VisitTicket.objects
            .filter(date=today, doctor=selected_doctor)
            .select_related("patient", "appointment")
            .order_by("number")
        )
        current_ticket = tickets_qs.filter(status="CALLING").first()

    # ──────────────────────
    # 處理櫃台按鈕 
    # ──────────────────────
    if request.method == "POST" and selected_doctor:
        action = request.POST.get("action")

        with transaction.atomic():
            tickets = (
                VisitTicket.objects
                .select_for_update()
                .filter(date=today, doctor=selected_doctor)
                .order_by("number")
            )
            current_ticket = tickets.filter(status="CALLING").first()

            # ▶ 開始 / 下一號
            if action == "start_next":
                # 1. 如果現在有在 CALLING 的號碼，先當作處理完成 
                if current_ticket:
                    current_ticket.status = "DONE"
                    current_ticket.finished_at = timezone.now()
                    fields = ["status", "finished_at"]

                    # 如果你也想同步 Appointment，就打開這幾行 
                    # if current_ticket.appointment_id:
                    #     appt = current_ticket.appointment
                    #     appt.status = Appointment.STATUS_DONE
                    #     appt.save(update_fields=["status"])

                    current_ticket.save(update_fields=fields)

                # 2. 找下一個 WAITING
                next_ticket = tickets.filter(status="WAITING").first()
                if not next_ticket:
                    messages.info(request, "目前沒有下一位候診中的病人 。")
                else:
                    next_ticket.status = "CALLING"
                    next_ticket.call_count = F("call_count") + 1
                    next_ticket.called_at = timezone.now()
                    next_ticket.save(update_fields=["status", "call_count", "called_at"])
                    messages.success(request, f"已叫號：第 {next_ticket.number} 號 。")

            # 🔄 重叫一次（同一個號碼再叫一次）
            elif action == "repeat":
                if not current_ticket:
                    messages.warning(request, "目前沒有正在叫的號碼 。")
                else:
                    current_ticket.call_count = F("call_count") + 1
                    current_ticket.called_at = timezone.now()
                    current_ticket.save(update_fields=["call_count", "called_at"])
                    messages.success(
                        request,
                        f"已重新叫號：第 {current_ticket.number} 號 。"
                    )

            # ⏭ 櫃台過號 + 下一號
            elif action == "skip":
                if not current_ticket:
                    messages.warning(request, "目前沒有可以過號的病人 。")
                else:
                    current_ticket.status = "NO_SHOW"
                    if hasattr(current_ticket, "is_skipped"):
                        current_ticket.is_skipped = True
                    if hasattr(current_ticket, "finished_at"):
                        current_ticket.finished_at = timezone.now()

                    fields = ["status"]
                    if hasattr(current_ticket, "is_skipped"):
                        fields.append("is_skipped")
                    if hasattr(current_ticket, "finished_at"):
                        fields.append("finished_at")
                    current_ticket.save(update_fields=fields)

                    # 找下一位 WAITING
                    next_ticket = tickets.filter(status="WAITING").first()
                    if next_ticket:
                        next_ticket.status = "CALLING"
                        next_ticket.call_count = F("call_count") + 1
                        next_ticket.called_at = timezone.now()
                        next_ticket.save(
                            update_fields=["status", "call_count", "called_at"]
                        )
                        messages.success(
                            request,
                            f"已標記過號，改叫第 {next_ticket.number} 號 。"
                        )
                    else:
                        messages.info(
                            request,
                            "已標記過號，目前沒有下一位候診病人 。"
                        )

            # 🆕 從列表叫回某一個已過號病人 
            elif action == "recall_ticket":
                ticket_id = request.POST.get("ticket_id")
                target = tickets.filter(pk=ticket_id).first()

                if not target:
                    messages.error(request, "找不到要叫回的號碼 。")
                elif target.status != "NO_SHOW":
                    messages.warning(request, "只能叫回已標記為未到（NO_SHOW）的號碼 。")
                else:
                    # 如果現在已經在叫別人，就先還原回 WAITING  
                    if current_ticket and current_ticket.id != target.id:
                        current_ticket.status = "WAITING"
                        current_ticket.save(update_fields=["status"])

                    target.status = "CALLING"
                    target.call_count = F("call_count") + 1
                    target.called_at = timezone.now()
                    target.save(update_fields=["status", "call_count", "called_at"])

                    messages.success(
                        request,
                        f"已叫回第 {target.number} 號 。"
                    )

        # POST 完後 redirect，避免重新整理重送表單 
        url = reverse("queues:reception_call")
        if selected_doctor:
            url += f"?doctor={selected_doctor.id}"
        return redirect(url)

    # ──────────────────────
    # GET → 顯示畫面 
    # ──────────────────────
    context = {
        "today": today,
        "doctors": doctors,
        "selected_doctor": selected_doctor,
        "tickets": tickets_qs,
        "current_ticket": current_ticket,
    }
    return render(request, "queues/reception_call.html", context)




@group_required("DOCTOR")
def doctor_panel(request):
    doctor = Doctor.objects.filter(user=request.user).first()
    if not doctor:
        messages.error(request, "目前帳號沒有綁定醫師資料 。")
        return redirect("index")

    today = timezone.localdate()

    # 叫號列表
    tickets_qs = (
        VisitTicket.objects
        .filter(date=today, doctor=doctor)
        .select_related("patient", "appointment")
        .order_by("appointment__time", "number")
    )

    current_ticket = tickets_qs.filter(status="CALLING").first()
    WAITING_tickets = tickets_qs.filter(status__in=["WAITING", "NO_SHOW"])
    done_tickets = tickets_qs.filter(status="DONE")

    today_appointments = (
        Appointment.objects
        .filter(doctor=doctor, date=today)
        .select_related("patient")
        .order_by("time")
    )

    # =============================
    # POST：醫師操作區塊
    # =============================
    if request.method == "POST":
        action = request.POST.get("action")
        ticket_id = request.POST.get("ticket_id")

        # ▶ 叫下一位
        if action == "call_next":
            next_ticket = tickets_qs.filter(status="WAITING").first()

            if not next_ticket:
                messages.warning(request, "沒有候診中的病人 。")
                return redirect("queues:doctor_panel")

            # 把舊 CALLING 的退回 WAITING
            tickets_qs.filter(status="CALLING").update(status="WAITING")

            next_ticket.status = "CALLING"
            next_ticket.called_at = timezone.now()
            next_ticket.call_count += 1
            next_ticket.save(update_fields=["status", "called_at", "call_count"])

            messages.success(request, f"已叫號：第 {next_ticket.number} 號 。")
            return redirect("queues:doctor_panel")

        # ▶ 看診完成
        elif action == "finish":
            ticket = get_object_or_404(tickets_qs, pk=ticket_id)

            ticket.status = "DONE"
            ticket.finished_at = timezone.now()
            ticket.save(update_fields=["status", "finished_at"])

            # 同步 Appointment
            if ticket.appointment_id:
                appt = ticket.appointment
                appt.status = Appointment.STATUS_DONE
                appt.save(update_fields=["status"])

            messages.success(request, f"{ticket.number} 號看診完成 。")
            return redirect("queues:doctor_panel")

        # ▶ 過號 → NO_SHOW + 叫下一位
        elif action == "skip":
            if current_ticket:
                current_ticket.status = "NO_SHOW"
                current_ticket.finished_at = timezone.now()
                current_ticket.save(update_fields=["status", "finished_at"])

                # 同步 Appointment
                if current_ticket.appointment_id:
                    appt = current_ticket.appointment
                    appt.status = Appointment.STATUS_NO_SHOW
                    appt.save(update_fields=["status"])

            # 找下一位
            next_ticket = tickets_qs.filter(status="WAITING").first()

            if next_ticket:
                next_ticket.status = "CALLING"
                next_ticket.called_at = timezone.now()
                next_ticket.call_count += 1
                next_ticket.save(update_fields=["status", "called_at", "call_count"])
                messages.success(request, f"已過號。下一位：{next_ticket.number} 號 。")
            else:
                messages.info(request, "已過號，目前沒有下一位 。")

            return redirect("queues:doctor_panel")

        # ▶ 叫回（NO_SHOW → CALLING）
        elif action == "recall":
            ticket = get_object_or_404(tickets_qs, pk=ticket_id)

            # 其他 CALLING 的退回 WAITING
            tickets_qs.exclude(pk=ticket.pk).filter(status="CALLING").update(status="WAITING")

            ticket.status = "CALLING"
            ticket.call_count += 1
            ticket.called_at = timezone.now()
            ticket.save(update_fields=["status", "call_count", "called_at"])

            messages.success(request, f"已重新叫號：第 {ticket.number} 號 。")
            return redirect("queues:doctor_panel")

    # =============================
    # 🆕 今天被藥師退回的處方
    # =============================
    rejected_prescriptions = (
        Prescription.objects
        .filter(
            doctor=doctor,
            date=today,
            verify_status=Prescription.VERIFY_REJECTED,
        )
        .select_related("patient")
        .order_by("-date", "-id")
    )

    # debug 想看的話可以暫時打開這行 ：
    # print("REJECTED:", list(rejected_prescriptions.values_list("id", flat=True)))

    # =============================
    # GET / 最後組 context
    # =============================
    context = {
        "doctor": doctor,
        "today": today,

        "tickets": tickets_qs,
        "current_ticket": current_ticket,
        "WAITING_tickets": WAITING_tickets,
        "done_tickets": done_tickets,

        "today_appointments": today_appointments,

        # 🆕 丟進 template 給你顯示提醒 
        "rejected_prescriptions": rejected_prescriptions,
    }

    return render(request, "queues/doctor_panel.html", context)




@group_required("DOCTOR")
def doctor_action(request, pk, act):
    # 之後你再補真正的功能
    return HttpResponse(f"Doctor action: id={pk}, action={act}")

def board(request):
    today = timezone.localdate()

    # 1️⃣ 先把所有啟用中的醫師抓出來，給前端下拉選單用 
    doctors = Doctor.objects.filter(is_active=True).order_by("name")

    # 2️⃣ 看 URL 有沒有帶 ?doctor=ID
    doctor_id = request.GET.get("doctor")
    selected_doctor = None

    tickets_today = (
        VisitTicket.objects
        .filter(date=today)
        .select_related("doctor", "patient")
    )

    if doctor_id:
        # 如果指定醫師，就只看那一位 
        selected_doctor = get_object_or_404(Doctor, pk=doctor_id, is_active=True)
        tickets_today = tickets_today.filter(doctor=selected_doctor)

    # 排序（就算只一位醫師也沒關係 ）
    tickets_today = tickets_today.order_by("doctor__name", "number")

    # 3️⃣ 一樣用原本的分組邏輯
    grouped = {}
    for t in tickets_today:
        info = grouped.setdefault(
            t.doctor_id,
            {
                "doctor": t.doctor,
                "current": None,
                "next": None,
                "done": [],
            },
        )

        if t.status in ("CALLING", "IN_PROGRESS") and info["current"] is None:
            info["current"] = t
        elif t.status == "WAITING" and info["next"] is None:
            info["next"] = t
        elif t.status == "DONE":
            if len(info["done"]) < 5:
                info["done"].append(t)

    board_data = list(grouped.values())

    context = {
        "today": today,
        "board_data": board_data,
        "doctors": doctors,
        "selected_doctor": selected_doctor,
    }
    return render(request, "queues/board.html", context)

def api_current_number(request):
    """
    回傳指定醫師今天的叫號資訊，給 Python → Arduino 用 
    GET 參數：
      - doctor_id: 醫師 ID (Doctor.pk)
    回傳 JSON：
      {
        "doctor": {...},
        "current": {...} 或 null,
        "next": {...} 或 null,
        "last_done": {...} 或 null,
        "timestamp": "ISO 時間"
      }
    """
    doctor_id = request.GET.get("doctor_id")
    if not doctor_id:
        return JsonResponse({"error": "doctor_id is required"}, status=400)

    try:
        doctor = Doctor.objects.get(pk=doctor_id, is_active=True)
    except Doctor.DoesNotExist:
        return JsonResponse({"error": "doctor not found"}, status=404)

    today = timezone.localdate()

    tickets = (
        VisitTicket.objects
        .filter(date=today, doctor=doctor)
        .select_related("patient")
        .order_by("number")
    )

    current = tickets.filter(status__in=["CALLING", "IN_PROGRESS"]).first()
    next_ticket = tickets.filter(status="WAITING").first()
    last_done = tickets.filter(status="DONE").order_by("-finished_at").first()

    def _ticket_to_dict(t):
        if not t:
            return None
        return {
            "id": t.id,
            "number": t.number,
            "patient_name": t.patient.full_name if t.patient_id else "",
            "chart_no": getattr(t.patient, "chart_no", None) if t.patient_id else None,
            "status": t.status,
        }

    data = {
        "doctor": {
            "id": doctor.id,
            "name": doctor.name,
            "department": doctor.department,
            "room": doctor.room,
        },
        "current": _ticket_to_dict(current),
        "next": _ticket_to_dict(next_ticket),
        "last_done": _ticket_to_dict(last_done),
        "timestamp": timezone.now().isoformat(),
    }
    return JsonResponse(data)