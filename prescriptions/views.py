from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages  

from common.utils import group_required
from django.contrib.auth.decorators import login_required

from .models import Prescription, PrescriptionItem
from .forms import PrescriptionForm, PrescriptionItemFormSet

from inventory.utils import use_drug
from queues.models import VisitTicket
from doctors.models import Doctor
from django.http import HttpResponseForbidden

from patients.models import Patient

from django.db.models import Count

@group_required("PHARMACY")
def pharmacy_panel(request):
    today = timezone.localdate()
    items = Prescription.objects.filter(
        date=today,
        status__in=["READY", "DISPENSED"]
    )
    return render(request, "prescriptions/pharmacy.html", {"items": items})


@group_required("PHARMACY")
def dispense(request, pk):
    rx = get_object_or_404(Prescription, pk=pk)

    if rx.status == "DISPENSED":
        return redirect("prescriptions:pharmacy_panel")

    # 簡單扣庫存喵
    for item in rx.items.all():
        # PrescriptionItem 有 qty 欄位喵（不是 quantity）
        use_drug(item.drug.code, item.quantity, ref=f"RX#{rx.pk}")

    rx.status = "DISPENSED"
    rx.save()
    return redirect("prescriptions:pharmacy_panel")


@group_required("DOCTOR")
def edit_for_ticket(request, ticket_id):
    """
    醫師針對某一張掛號票(VisitTicket) 開 / 編輯 處方籤
    URL 例子：/prescriptions/ticket/117/
    """
    ticket = get_object_or_404(VisitTicket, id=ticket_id)

    prescription, created = Prescription.objects.get_or_create(
        patient=ticket.patient,
        doctor=ticket.doctor,
        date=ticket.date,
        defaults={"status": "draft"},
    )

    if request.method == "POST":
        form = PrescriptionForm(request.POST, instance=prescription)
        items = PrescriptionItemFormSet(request.POST, instance=prescription)

        if form.is_valid() and items.is_valid():
            form.save()
            items.save()
            messages.success(request, "處方已儲存")
            return redirect("queues:doctor_panel")
    else:
        form = PrescriptionForm(instance=prescription)
        items = PrescriptionItemFormSet(instance=prescription)

    context = {
        "ticket": ticket,          # 雖然 template 現在沒用到，但留著沒關係
        "prescription": prescription,  # 👈 重要：給 template 用
        "form": form,
        "items": items,
    }
    return render(request, "prescriptions/prescription_form.html", context)

@group_required("DOCTOR")
def edit_prescription(request, pk):
    """
    醫師從『處方歷史列表』點進來編輯某一張處方
    """
    doctor = get_object_or_404(Doctor, user=request.user)
    prescription = get_object_or_404(Prescription, pk=pk, doctor=doctor)

    if request.method == "POST":
        form = PrescriptionForm(request.POST, instance=prescription)
        items = PrescriptionItemFormSet(request.POST, instance=prescription)

        if form.is_valid() and items.is_valid():
            form.save()
            items.save()
            messages.success(request, "處方已更新")
            return redirect("prescriptions:doctor_prescription_list")
    else:
        form = PrescriptionForm(instance=prescription)
        items = PrescriptionItemFormSet(instance=prescription)

    context = {
        "prescription": prescription,
        "form": form,
        "items": items,
        "ticket": None,  # 這裡沒有 ticket，給 template 一個空的也沒差
    }
    return render(request, "prescriptions/prescription_form.html", context)


@group_required("DOCTOR")
def doctor_prescription_list(request):
    """
    醫師自己的處方歷史列表喵
    """
    # 1. 找出目前登入的醫師喵
    doctor = get_object_or_404(Doctor, user=request.user)

    # 2. 把這位醫師開過的處方抓出來喵
    prescriptions = (
        Prescription.objects
        .filter(doctor=doctor)
        .select_related("patient")           # 會用到病人資料喵
        .prefetch_related("items__drug")     # 預先抓用藥項目 + 藥品喵
        .annotate(item_count=Count("items")) # 每張處方有幾個項目喵
        .order_by("-date", "-created_at")    # 最近的排前面喵
    )

    context = {
        "doctor": doctor,
        "prescriptions": prescriptions,
    }
    return render(request, "prescriptions/doctor_prescription_list.html", context)


@group_required("PATIENT")
def patient_prescription_list(request):
    """
    病人自己的處方歷史列表喵
    """
    # 1. 找出目前登入的病人喵
    patient = get_object_or_404(Patient, user=request.user)

    # 2. 抓這個病人的所有處方
    prescriptions = (
        Prescription.objects
        .filter(patient=patient)
        .select_related("doctor")          # 會顯示醫生資料喵
        .prefetch_related("items__drug")   # 之後看明細用喵
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


@group_required("PATIENT")
def patient_prescription_detail(request, pk):
    """
    病人查看單一處方明細喵
    """
    patient = get_object_or_404(Patient, user=request.user)

    prescription = get_object_or_404(
        Prescription.objects
        .select_related("doctor", "patient")
        .prefetch_related("items__drug"),
        pk=pk,
        patient=patient,   # 保證是自己的處方喵
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
    病人查看自己的處方歷史喵
    """
    patient = getattr(request.user, "patient", None)
    if patient is None:
        # 不是病人帳號就不讓看喵
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
    """
    醫師 / 病人查看處方明細（唯讀）喵
    """
    prescription = get_object_or_404(
        Prescription.objects
        .select_related("patient", "doctor", "doctor__user")
        .prefetch_related("items__drug"),
        pk=pk,
    )

    user = request.user

    # 權限檢查喵：只有該處方的醫師或病人可以看
    can_see = False
    if hasattr(user, "doctor") and user.doctor == prescription.doctor:
        can_see = True
    if hasattr(user, "patient") and user.patient == prescription.patient:
        can_see = True

    if not can_see:
        return HttpResponseForbidden("你沒有權限查看這張處方喵")

    context = {
        "prescription": prescription,
    }
    return render(request, "prescriptions/prescription_detail.html", context)
