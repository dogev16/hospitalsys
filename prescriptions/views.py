from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from appointments.models import Appointment
from common.utils import group_required
from public.models import PublicRegistrationRequest

from django.db.models import Max

from .models import (
    Prescription,
    PrescriptionItem,
    PrescriptionLog,
    PrescriptionAuditLog,
)
from .forms import PrescriptionForm, PrescriptionItemFormSet


from inventory.utils import adjust_stock, can_dispense_item, preview_use_drug_from_prescription_item, use_drug_from_prescription_item
from queues.models import VisitTicket
from doctors.models import Doctor
from patients.models import Patient
from django.db import transaction




@group_required("PHARMACY")
def pharmacy_panel(request):
    today = timezone.localdate()

    prescriptions = (
        Prescription.objects
        .filter(
            date=today,
            status=Prescription.STATUS_FINAL,
            pharmacy_status=Prescription.PHARMACY_PENDING,
            verify_status=Prescription.VERIFY_APPROVED,
        )
        .select_related("patient", "doctor__user")
        .prefetch_related("items__drug")
        .order_by("date", "id")
    )

    MIN_VALID_DAYS = 7

    rx_rows = []
    for rx in prescriptions:
        items = list(rx.items.all())
        problems = []

        for it in items:
            res = can_dispense_item(it, min_valid_days=MIN_VALID_DAYS)

            if isinstance(res, (tuple, list)):
                ok = bool(res[0]) if len(res) >= 1 else False
                reason = str(res[1]) if len(res) >= 2 else ""
            else:
                ok = bool(res)
                reason = ""

            if not ok:
                problems.append(reason or f"{it.drug.name} 無法領藥（原因未知）")

        rx_rows.append({
            "rx": rx,
            "can_dispense": (len(problems) == 0),
            "problems": problems,
        })

    return render(request, "prescriptions/pharmacy_panel.html", {
        "today": today,
        "rx_rows": rx_rows,
        "min_valid_days": MIN_VALID_DAYS,
    })




def add_prescription_log(prescription, action, message="", user=None):

    PrescriptionLog.objects.create(
        prescription=prescription,
        action=action,
        message=message,
        operator=user,
    )


@group_required("PHARMACY")
@transaction.atomic
def dispense(request, pk):
    prescription = get_object_or_404(
        Prescription.objects
        .select_related("patient", "doctor__user")
        .prefetch_related("items__drug"),
        pk=pk,
    )

    if prescription.verify_status != Prescription.VERIFY_APPROVED:
        messages.error(request, "此處方尚未通過藥師審核，不能領藥 。")
        return redirect("prescriptions:pharmacy_panel")

    if prescription.pharmacy_status == Prescription.PHARMACY_CANCELLED:
        messages.error(request, "此處方已作廢或退藥，不能再領藥 。")
        return redirect("prescriptions:pharmacy_panel")

    if prescription.pharmacy_status == Prescription.PHARMACY_DONE:
        messages.warning(request, "此處方已完成領藥，無需再次操作 。")
        return redirect("prescriptions:pharmacy_panel")

    items = list(prescription.items.all())

    has_shortage = any(
        item.drug.stock_quantity < item.quantity
        for item in items
    )

    if request.method == "POST":
        action = request.POST.get("action", "complete")

        if action == "complete":
            insufficient = []
            for item in items:
                drug = item.drug
                if drug.stock_quantity < item.quantity:
                    insufficient.append((drug, drug.stock_quantity, item.quantity))

            if insufficient:
                msg_lines = []
                for drug, stock, need in insufficient:
                    msg_lines.append(f"{drug.name} 庫存不足（現有 {stock}，需要 {need}）")
                messages.error(request, "無法完成領藥 ：\n" + "\n".join(msg_lines))
                return redirect("prescriptions:pharmacy_panel")

            for item in items:
                use_drug_from_prescription_item(
                    item,
                    prescription=prescription,
                    operator=request.user,
                )

            prescription.pharmacy_status = Prescription.PHARMACY_DONE
            prescription.dispensed_at = timezone.now()
            prescription.dispensed_by = request.user  

            if prescription.status != Prescription.STATUS_FINAL:
                prescription.status = Prescription.STATUS_FINAL

            prescription.save()

            add_prescription_log(
                prescription,
                PrescriptionLog.ACTION_DISPENSE,
                "藥局完成領藥並扣庫存",
                user=request.user,
            )

            PrescriptionAuditLog.objects.create(
                prescription=prescription,
                action="DISPENSE",
                performed_by=request.user,
                detail="藥局完成領藥並扣庫存",
            )

            messages.success(request, f"處方 #{prescription.id} 已完成領藥 ！")
            return redirect("prescriptions:pharmacy_panel")


        messages.error(request, "未知的動作 ，請再試一次。")
        return redirect("prescriptions:pharmacy_panel")

    context = {
        "prescription": prescription,
        "items": items,
        "has_shortage": has_shortage,
    }
    return render(request, "prescriptions/pharmacy_dispense.html", context)


@group_required("PHARMACY")
def pharmacy_review_list(request):

    today = timezone.localdate()

    prescriptions = (
        Prescription.objects
        .filter(
            date=today,
            status=Prescription.STATUS_FINAL,
            verify_status=Prescription.VERIFY_PENDING,  
        )
        .select_related("patient", "doctor__user")
        .prefetch_related("items__drug")
        .order_by("date", "id")
    )

    context = {
        "prescriptions": prescriptions,
        "today": today,
    }
    return render(request, "prescriptions/pharmacy_review_list.html", context)


@group_required("PHARMACY")
@transaction.atomic
def pharmacy_review_detail(request, pk):

    prescription = get_object_or_404(
        Prescription.objects
        .select_related("patient", "doctor__user")
        .prefetch_related("items__drug"),
        pk=pk,
    )

    if prescription.status != Prescription.STATUS_FINAL:
        messages.error(request, "此處方尚未完成，無法審核 。")
        return redirect("prescriptions:pharmacy_review_list")

    if request.method == "POST":
        action = request.POST.get("action")
        note = (request.POST.get("verify_note") or "").strip()

        if action == "approve":
            prescription.verify_status = Prescription.VERIFY_APPROVED
            prescription.verified_by = request.user
            prescription.verified_at = timezone.now()
            prescription.verify_note = note
            prescription.save(update_fields=[
                "verify_status",
                "verified_by",
                "verified_at",
                "verify_note",
            ])

            msg = "藥師審核通過"
            if note:
                msg += f"（備註：{note}）"
            add_prescription_log(
                prescription,
                PrescriptionLog.ACTION_UPDATE,
                msg,
                user=request.user,
            )

            PrescriptionAuditLog.objects.create(
                prescription=prescription,
                action="UPDATE",
                performed_by=request.user,
                detail=f"藥師審核通過。verify_status=approved；note={note}",
            )

            messages.success(request, f"處方 #{prescription.id} 已通過審核 ！")
            return redirect("prescriptions:pharmacy_review_list")

        elif action == "reject":
            prescription.verify_status = Prescription.VERIFY_REJECTED
            prescription.verified_by = request.user
            prescription.verified_at = timezone.now()
            prescription.verify_note = note or "處方需醫師修正"
            prescription.save(update_fields=[
                "verify_status",
                "verified_by",
                "verified_at",
                "verify_note",
            ])

            add_prescription_log(
                prescription,
                PrescriptionLog.ACTION_UPDATE,
                f"藥師退回處方。原因：{prescription.verify_note}",
                user=request.user,
            )

            PrescriptionAuditLog.objects.create(
                prescription=prescription,
                action="UPDATE",
                performed_by=request.user,
                detail=f"藥師退回處方。verify_status=rejected；note={prescription.verify_note}",
            )

            messages.warning(request, f"處方 #{prescription.id} 已退回醫師 。")
            return redirect("prescriptions:pharmacy_review_list")
        else:
            messages.error(request, "未知的審核動作 ，請再試一次。")
            return redirect("prescriptions:pharmacy_review_list")

    logs = (
        PrescriptionLog.objects
        .filter(prescription=prescription)
        .select_related("operator")
        .order_by("-created_at")
    )
    audit_logs = (
        PrescriptionAuditLog.objects
        .filter(prescription=prescription)
        .select_related("performed_by")
        .order_by("-created_at")
    )

    context = {
        "prescription": prescription,
        "logs": logs,
        "audit_logs": audit_logs,
    }
    return render(request, "prescriptions/pharmacy_review_detail.html", context)





@group_required("DOCTOR")
def edit_for_ticket(request, ticket_id):

    print("=== [DEBUG] edit_for_ticket 進來了 ，method =", request.method)

    ticket = get_object_or_404(VisitTicket, id=ticket_id)

    doctor = get_object_or_404(Doctor, user=request.user)
    if ticket.doctor != doctor:
        messages.error(request, "你不是這張掛號票的醫師 ，不能開處方。")
        return redirect("queues:doctor_panel")

    prescription, created = Prescription.objects.get_or_create(
        visit_ticket=ticket,
        defaults={
            "patient": ticket.patient,
            "doctor": ticket.doctor,
            "date": ticket.date,   
            "status": Prescription.STATUS_DRAFT,
        },
    )

    if request.method == "POST":
        print("=== [DEBUG] 收到 POST 了 ！POST 內容：", request.POST)

        form = PrescriptionForm(request.POST, instance=prescription)
        items = PrescriptionItemFormSet(request.POST, instance=prescription)

        print("=== [DEBUG] form.is_valid():", form.is_valid())
        print("=== [DEBUG] form.errors:", form.errors)
        print("=== [DEBUG] items.is_valid():", items.is_valid())
        print("=== [DEBUG] items.errors:", items.errors)
        print("=== [DEBUG] items.non_form_errors():", items.non_form_errors())

        if form.is_valid() and items.is_valid():
            prescription = form.save(commit=False)
            prescription.patient = ticket.patient
            prescription.doctor = ticket.doctor
            prescription.date = ticket.date

            prescription.status = Prescription.STATUS_FINAL
            prescription.verify_status = Prescription.VERIFY_PENDING
            prescription.verified_by = None
            prescription.verified_at = None
            prescription.verify_note = ""

            prescription.save()

            items.instance = prescription
            items.save()

            add_prescription_log(
                prescription,
                PrescriptionLog.ACTION_UPDATE,
                "醫師儲存處方內容",
                user=request.user,
            )

            print("=== [DEBUG] 處方已成功儲存 ，準備 redirect ===")
            messages.success(request, "處方已儲存 ！")
            return redirect("queues:doctor_panel")
        else:
            print("=== [DEBUG] 表單驗證沒過 ，會回到同一頁並顯示錯誤 ===")
            messages.error(request, "表單有錯誤 ，請檢查紅色欄位。")

    else:
        form = PrescriptionForm(instance=prescription)
        items = PrescriptionItemFormSet(instance=prescription)

    context = {
        "ticket": ticket,
        "prescription": prescription,
        "form": form,
        "items": items,
        "patient": ticket.patient,
    }
    return render(request, "prescriptions/prescription_form.html", context)


@group_required("DOCTOR")
def edit_prescription(request, pk):

    doctor = get_object_or_404(Doctor, user=request.user)
    prescription = get_object_or_404(Prescription, pk=pk, doctor=doctor)

    if prescription.pharmacy_status != Prescription.PHARMACY_PENDING:
        messages.error(request, "此處方已經由藥局處理，無法再修改 。")
        return redirect("prescriptions:doctor_prescription_list")

    if request.method == "POST":
        form = PrescriptionForm(request.POST, instance=prescription)
        items = PrescriptionItemFormSet(request.POST, instance=prescription)

        if form.is_valid() and items.is_valid():
            prescription_obj = form.save(commit=False)

            prescription_obj.status = Prescription.STATUS_FINAL
            prescription_obj.verify_status = Prescription.VERIFY_PENDING
            prescription_obj.verified_by = None
            prescription_obj.verified_at = None
            prescription_obj.verify_note = ""

            prescription_obj.save()
            items.instance = prescription_obj
            items.save()

            add_prescription_log(
                prescription_obj,
                PrescriptionLog.ACTION_UPDATE,
                "醫師修改處方內容",
                user=request.user,
            )

            messages.success(request, "處方已更新並送出 ！")
            return redirect("prescriptions:doctor_prescription_list")
    else:
        form = PrescriptionForm(instance=prescription)
        items = PrescriptionItemFormSet(instance=prescription)

    context = {
        "prescription": prescription,
        "form": form,
        "items": items,
        "ticket": None, 
        "patient": prescription.patient,
    }
    return render(request, "prescriptions/prescription_form.html", context)


@group_required("DOCTOR")
def doctor_prescription_list(request):

    doctor = Doctor.objects.filter(user=request.user).first()
    if not doctor:
        messages.error(request, "找不到對應的醫師資料 ，請聯絡系統管理員。")
        return redirect("index")

    prescriptions = (
        Prescription.objects
        .filter(doctor=doctor)
        .select_related("patient")
        .prefetch_related("items__drug")
        .order_by("-date", "-created_at")
    )

    context = {
        "doctor": doctor,
        "prescriptions": prescriptions,
    }
    return render(request, "prescriptions/doctor_prescription_list.html", context)



@login_required
@group_required("PATIENT")
def patient_prescription_list(request):

    patient = get_object_or_404(Patient, chart_no=request.user.username)

    prescriptions = (
        Prescription.objects
        .filter(patient=patient)
        .select_related("doctor")
        .prefetch_related("items__drug")
        .order_by("-date", "-created_at")
    )

    context = {
        "patient": patient,
        "prescriptions": prescriptions,
    }
    return render(
        request,
        "prescriptions/patient_prescription_list.html",
        context,
    )


@login_required
@group_required("PATIENT")
def patient_prescription_detail(request, pk):

    patient = get_object_or_404(Patient, user=request.user)

    prescription = get_object_or_404(
        Prescription.objects
        .select_related("doctor", "patient")
        .prefetch_related("items__drug"),
        pk=pk,
        patient=patient,   
    )

    context = {
        "patient": patient,
        "rx": prescription,
    }
    return render(
        request,
        "prescriptions/patient_prescription_detail.html",
        context,
    )


@login_required
def patient_history(request):
    """
    病人查看自己的處方歷史 （舊版路由，如果還有用就保留）
    """
    patient = getattr(request.user, "patient", None)
    if patient is None:
        return redirect("core:home")

    prescriptions = (
        Prescription.objects
        .filter(patient=patient)
        .select_related("doctor", "patient")
        .prefetch_related("items__drug")
        .order_by("-date", "-created_at")
    )

    context = {
        "prescriptions": prescriptions,
        "patient": patient,
    }
    return render(request, "prescriptions/patient_history.html", context)



@login_required
def prescription_detail(request, pk):
    prescription = get_object_or_404(
        Prescription.objects
        .select_related("patient", "doctor", "doctor__user")
        .prefetch_related("items__drug"),
        pk=pk,
    )

    user = request.user

    is_doctor_owner = hasattr(user, "doctor") and user.doctor == prescription.doctor
    is_patient_owner = hasattr(user, "patient") and user.patient == prescription.patient
    is_pharmacy = user.groups.filter(name="PHARMACY").exists() or user.is_superuser

    is_doctor = is_doctor_owner
    is_patient = is_patient_owner

    if not (is_doctor_owner or is_patient_owner or is_pharmacy):
        return HttpResponseForbidden("你沒有權限查看這張處方 。")

    logs = (
        PrescriptionLog.objects
        .filter(prescription=prescription)
        .select_related("operator")
        .order_by("-created_at")
    )

    audit_logs = (
        PrescriptionAuditLog.objects
        .filter(prescription=prescription)
        .select_related("performed_by")
        .order_by("-created_at")
    )

    context = {
        "prescription": prescription,
        "logs": logs,
        "audit_logs": audit_logs,
        "is_doctor": is_doctor,
        "is_patient": is_patient,
        "is_pharmacy": is_pharmacy,
    }

    return render(request, "prescriptions/prescription_detail.html", context)


@group_required("PHARMACY")
@transaction.atomic
def cancel_or_return_prescription(request, pk):
    prescription = get_object_or_404(
        Prescription.objects.prefetch_related("items__drug"),
        pk=pk
    )

    if prescription.pharmacy_status == Prescription.PHARMACY_CANCELLED:
        messages.warning(request, "這張處方已經作廢過 。")
        return redirect("prescriptions:pharmacy_panel")

    if request.method == "POST":

        if prescription.pharmacy_status == Prescription.PHARMACY_PENDING:
            prescription.pharmacy_status = Prescription.PHARMACY_CANCELLED
            prescription.save()

            add_prescription_log(
                prescription,
                PrescriptionLog.ACTION_CANCEL,
                "處方尚未領藥，藥局作廢處方",
                user=request.user,
            )

            PrescriptionAuditLog.objects.create(
                prescription=prescription,
                action="CANCEL",
                performed_by=request.user,
                detail="處方尚未領藥，藥局作廢處方（不動庫存）",
            )

            messages.success(request, f"處方 #{prescription.id} 已作廢 ！")
            return redirect("prescriptions:pharmacy_panel")

        if prescription.pharmacy_status == Prescription.PHARMACY_DONE:

            for item in prescription.items.all():
                adjust_stock(
                    drug=item.drug,
                    change=+item.quantity,   
                    reason="return",
                    note=f"處方 #{prescription.id} 退藥",
                    prescription=prescription,
                    operator=request.user,
                )

            prescription.pharmacy_status = Prescription.PHARMACY_CANCELLED
            prescription.save()

            add_prescription_log(
                prescription,
                PrescriptionLog.ACTION_RETURN,
                "已發藥，藥局退藥並作廢處方，庫存加回",
                user=request.user,
            )

            PrescriptionAuditLog.objects.create(
                prescription=prescription,
                action="RETURN",
                performed_by=request.user,
                detail="已發藥，藥局退藥並作廢處方，庫存加回",
            )

            messages.success(request, f"處方 #{prescription.id} 已退藥並作廢 ！")
            return redirect("prescriptions:pharmacy_panel")

    return render(request, "prescriptions/cancel_or_return_confirm.html", {
        "prescription": prescription,
    })

@login_required
@group_required("PHARMACY")
@transaction.atomic
def dispense_confirm(request, pk):
    prescription = get_object_or_404(
        Prescription.objects.prefetch_related("items__drug"),
        pk=pk,
    )
    items = list(prescription.items.all())

    MIN_VALID_DAYS = 7  


    checks = []
    for item in items:
        try:
            preview_use_drug_from_prescription_item(
                item,
                min_valid_days=MIN_VALID_DAYS,
            )
            checks.append({"item": item, "ok": True, "reason": ""})
        except ValueError as e:
            checks.append({"item": item, "ok": False, "reason": str(e)})

    has_shortage = any(not c["ok"] for c in checks)

    if request.method == "GET":
        return render(
            request,
            "prescriptions/pharmacy_dispense_confirm.html",
            {
                "prescription": prescription,
                "items": items,
                "checks": checks,
                "has_shortage": has_shortage,
                "min_valid_days": MIN_VALID_DAYS,
            },
        )


    if prescription.pharmacy_status != Prescription.PHARMACY_PENDING:
        messages.warning(request, "此處方已非待領藥狀態 。")
        return redirect("prescriptions:pharmacy_panel")

    if has_shortage:
        messages.error(request, "部分藥品效期或庫存不足，無法完成領藥 。")
        return redirect("prescriptions:dispense_confirm", pk=pk)

    try:
        for item in items:
            use_drug_from_prescription_item(
                item,
                operator=request.user,
                prescription=prescription,
                min_valid_days=MIN_VALID_DAYS,
            )
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("prescriptions:dispense_confirm", pk=pk)

    prescription.pharmacy_status = Prescription.PHARMACY_DONE
    prescription.dispensed_by = request.user
    prescription.dispensed_at = timezone.now()
    if prescription.status != Prescription.STATUS_FINAL:
        prescription.status = Prescription.STATUS_FINAL

    prescription.save(update_fields=["pharmacy_status", "dispensed_by", "dispensed_at", "status"])

    add_prescription_log(
        prescription,
        PrescriptionLog.ACTION_DISPENSE,
        "藥局完成領藥（經確認頁）並扣庫存",
        user=request.user,
    )
    PrescriptionAuditLog.objects.create(
        prescription=prescription,
        action="DISPENSE",
        performed_by=request.user,
        detail="藥局完成領藥（經確認頁）並扣庫存",
    )

    messages.success(request, f"處方 #{prescription.id} 已完成領藥 ！")
    return redirect("prescriptions:pharmacy_panel")


@login_required
@group_required("PHARMACY")    
def prescription_print(request, pk):
    prescription = get_object_or_404(
        Prescription.objects.select_related("patient", "doctor", "doctor__user")
                            .prefetch_related("items__drug"),
        pk=pk,
    )

    context = {
        "prescription": prescription,
        "items": prescription.items.all(),
    }
    return render(request, "prescriptions/prescription_print.html", context)


@group_required("PHARMACY")
def public_request_list(request):
    qs = (
        PublicRegistrationRequest.objects
        .select_related("doctor")
        .filter(status=PublicRegistrationRequest.STATUS_PENDING)
        .order_by("date", "time", "id")
    )
    return render(request, "prescriptions/public_request_list.html", {"requests": qs})


@require_POST
@transaction.atomic
def public_request_approve(request, pk):
    req = get_object_or_404(PublicRegistrationRequest.objects.select_for_update(), pk=pk)

    if req.status != "PENDING":
        messages.info(request, "這筆已處理過了 ")
        return redirect("prescriptions:public_request_list")

    patient, _ = Patient.objects.get_or_create(
        national_id=req.national_id,
        defaults={
            "full_name": req.name,
            "birth_date": req.birth_date,
            "phone": req.phone,
        }
    )

    appointment = Appointment.objects.create(
        patient=patient,
        doctor=req.doctor,
        date=req.date,
        time=req.time,
        status="SCHEDULED",  
    )

    today = timezone.localdate()
    next_no = (
        VisitTicket.objects.filter(doctor=req.doctor, date=req.date).count() + 1
    )

    VisitTicket.objects.create(
        appointment=appointment,
        date=req.date,
        doctor=req.doctor,
        patient=patient,
        number=next_no,
        status="WAITING",
    )

    req.status = "APPROVED"
    req.status = "APPROVED"
    req.appointment = appointment
    req.save(update_fields=["status", "appointment"])

    messages.success(request, "核准成功")
    return redirect("prescriptions:public_request_list")


@group_required("PHARMACY")
@transaction.atomic
def public_request_reject(request, pk):
    req = get_object_or_404(PublicRegistrationRequest, pk=pk)

    if req.status != PublicRegistrationRequest.STATUS_PENDING:
        messages.warning(request, "此申請單已處理過了 ")
        return redirect("prescriptions:public_request_list")

    req.status = PublicRegistrationRequest.STATUS_REJECTED
    req.save()
    messages.success(request, "已拒絕此申請 ")
    return redirect("prescriptions:public_request_list")