from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from common.utils import group_required
from .models import VisitTicket
from doctors.models import Doctor, DoctorSchedule

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from datetime import datetime
from django.urls import reverse
from django.contrib import messages


@group_required("RECEPTION")
def reception_panel(request):
    today = timezone.localdate()
    tickets = VisitTicket.objects.filter(date=today).order_by("doctor__name", "number")
    return render(request, "queues/reception.html", {"tickets": tickets})

@group_required("STAFF_RECEPTION")
def reception_call(request):
    today = timezone.localdate()
    doctor_id = request.GET.get("doctor")

    doctors = (
        DoctorSchedule.objects.filter(
            weekday=today.weekday(), is_active=True, doctor__is_active=True
        )
        .order_by("doctor__name")
        .select_related("doctor")
    )
    doctors_list = [s.doctor for s in doctors]

    selected_doctor = None
    if doctor_id:
        try:
            selected_doctor = next(
                d for d in doctors_list if str(d.pk) == str(doctor_id)
            )
        except StopIteration:
            selected_doctor = doctors_list[0] if doctors_list else None
    else:
        selected_doctor = doctors_list[0] if doctors_list else None

    tickets = VisitTicket.objects.filter(
        doctor=selected_doctor,
        date=today,
    ).select_related("patient", "doctor", "appointment").order_by("number")

    # 這邊會找出「目前叫號中」的號碼：如果有 calling 就用 calling，否則用下一個 waiting
    current_ticket = (
        tickets.filter(status="calling").order_by("number").first()
        or tickets.filter(status="waiting").order_by("number").first()
    )

    if request.method == "POST" and selected_doctor:
        action = request.POST.get("action")
        tickets = list(tickets)

        if action == "next":
            # 1. 把目前 calling 的改成 done
            if current_ticket and current_ticket.status == "calling":
                current_ticket.status = "done"
                current_ticket.finished_at = timezone.now()
                current_ticket.save(update_fields=["status", "finished_at"])

            # 2. 換下一個 waiting 的變成 calling
            next_ticket = (
                VisitTicket.objects.filter(
                    doctor=selected_doctor,
                    date=today,
                    status="waiting",
                )
                .order_by("appointment__time", "number")
                .first()
            )
            if next_ticket:
                next_ticket.status = "calling"
                next_ticket.called_at = timezone.now()
                next_ticket.save(update_fields=["status", "called_at"])
            else:
                # 👉 今天已經沒有 waiting 的號碼了
                messages.info(request, "今天已經沒有下一號可以叫了喵。")

        elif action == "recall":
            if current_ticket and current_ticket.status == "calling":
                current_ticket.called_at = timezone.now()
                current_ticket.save(update_fields=["called_at"])

        # PRG：避免重新整理重送表單
        return redirect(
            f"{reverse('queues:reception_call')}?doctor={selected_doctor.pk}"
        )

    # GET 重新抓一次最新狀態
    tickets = VisitTicket.objects.filter(
        doctor=selected_doctor,
        date=today,
    ).select_related("patient", "doctor", "appointment").order_by("number")

    current_ticket = (
        tickets.filter(status="calling").order_by("number").first()
        or tickets.filter(status="waiting").order_by("number").first()
    )

    context = {
        "today": today,
        "doctors": doctors_list,
        "selected_doctor": selected_doctor,
        "tickets": tickets,
        "current_ticket": current_ticket,
    }
    return render(request, "queues/reception_call.html", context)

def board(request):
    today = timezone.localdate()
    tickets = (
        VisitTicket.objects
        .filter(date=today)
        .order_by("doctor__name", "number")  # 這裡改成 name 
    )
    return render(request, "queues/board.html", {"tickets": tickets})



@group_required("DOCTOR")
def doctor_panel(request):
    """
    醫師叫號畫面：
    - 只看到自己今天的號碼
    - 狀態統一使用 waiting / calling / done
    """
    # 1. 找出這個登入帳號對應的 doctor
    doctor = Doctor.objects.filter(user=request.user).first()
    if not doctor:
        messages.error(request, "目前帳號沒有綁定醫師資料，請請管理員確認。")
        return redirect("index")  # 這裡用你的首頁 url name，如果不同再改

    today = timezone.localdate()

    # 2. 抓今天這位醫師所有號碼牌（依預約時間 + 號碼排序）
    tickets_qs = (
        VisitTicket.objects
        .filter(date=today, doctor=doctor)
        .select_related("patient", "appointment")
        .order_by("appointment__time", "number")
    )

    # 目前正在叫號的那一位（如果有）
    current_ticket = (
        tickets_qs
        .filter(status="calling")
        .order_by("number")
        .first()
    )

    # 3. 處理按鈕動作（POST）
    if request.method == "POST":
        action = request.POST.get("action")
        ticket_id = request.POST.get("ticket_id")

        # 叫下一位：找第一個 waiting 的
        if action == "call_next":
            next_ticket = (
                tickets_qs
                .filter(status="waiting")
                .order_by("appointment__time", "number")
                .first()
            )
            if not next_ticket:
                messages.warning(request, "今天沒有候診中的病人了喵。")
                return redirect("queues:doctor_panel")

            # 把其他 calling 清回 waiting（保險，避免同時兩個 calling）
            tickets_qs.filter(status="calling").update(status="waiting")

            next_ticket.status = "calling"
            next_ticket.called_at = timezone.now()
            next_ticket.save(update_fields=["status", "called_at"])
            messages.success(request, f"已叫號：第 {next_ticket.number} 號喵。")
            return redirect("queues:doctor_panel")

        # 看診完成
        if action == "finish":
            ticket = get_object_or_404(tickets_qs, pk=ticket_id)
            ticket.status = "done"
            ticket.finished_at = timezone.now()
            ticket.save(update_fields=["status", "finished_at"])
            messages.success(request, f"{ticket.number} 號看診完成喵。")
            return redirect("queues:doctor_panel")

    # 4. 首次進入或 GET 重新整理
    context = {
        "doctor": doctor,
        "today": today,
        "tickets": tickets_qs,
        "current_ticket": current_ticket,
    }
    return render(request, "queues/doctor_panel.html", context)

@group_required("DOCTOR")
def doctor_action(request, pk, act):
    # 之後你再補真正的功能
    return HttpResponse(f"Doctor action: id={pk}, action={act}")
