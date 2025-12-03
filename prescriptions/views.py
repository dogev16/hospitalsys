from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages  

from common.utils import group_required
from django.contrib.auth.decorators import login_required

from .models import Prescription, PrescriptionItem
from .forms import PrescriptionForm, PrescriptionItemFormSet

from inventory.utils import use_drug
from inventory.models import Drug, StockTransaction
from queues.models import VisitTicket
from doctors.models import Doctor
from django.http import HttpResponseForbidden

from patients.models import Patient

from django.db.models import Count

@group_required("PHARMACY")
def pharmacy_panel(request):
    today = timezone.localdate()

    prescriptions = (
        Prescription.objects
        .filter(date=today, status="READY")     # 只顯示待領藥的
        .select_related("patient", "doctor")
        .prefetch_related("items__drug")
        .order_by("-date")
    )

    context = {
        "prescriptions": prescriptions,
    }
    return render(request, "prescriptions/pharmacy_panel.html", context)




@group_required("PHARMACY")
def dispense(request, pk):
    """
    領藥動作：
    - 檢查庫存是否足夠
    - 扣庫存 & 建立 StockTransaction
    - 將處方狀態改為 dispensed
    """
    prescription = get_object_or_404(
        Prescription.objects.select_related("patient", "doctor").prefetch_related("items__drug"),
        pk=pk,
    )

    if request.method == "POST":
        # 1. 先檢查全部項目庫存是否足夠喵
        insufficient = []
        for item in prescription.items.all():
            drug = item.drug
            if drug.stock_quantity < item.quantity:
                insufficient.append((drug, drug.stock_quantity, item.quantity))

        if insufficient:
            msg_lines = []
            for drug, stock, need in insufficient:
                msg_lines.append(f"{drug.name} 庫存不足（現有 {stock}，需要 {need}）")
            messages.error(request, "無法完成領藥喵：\n" + "\n".join(msg_lines))
            return redirect("prescriptions:pharmacy_panel")

        # 2. 扣庫存 + 寫入異動紀錄喵
        for item in prescription.items.all():
            drug = item.drug
            drug.stock_quantity -= item.quantity
            drug.save()

            StockTransaction.objects.create(
                drug=drug,
                change=-item.quantity,
                reason="dispense",
                prescription=prescription,
                note=f"處方 #{prescription.id} 領藥",
            )

        # 3. 更新處方狀態喵
        prescription.status = "dispensed"
        prescription.save()

        messages.success(request, f"處方 #{prescription.id} 已完成領藥喵！")
        return redirect("prescriptions:pharmacy_panel")

    # GET：顯示確認頁面喵
    context = {
        "prescription": prescription,
    }
    return render(request, "prescriptions/pharmacy_dispense_confirm.html", context)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse

from common.utils import group_required
from queues.models import VisitTicket
from doctors.models import Doctor
from .models import Prescription
from .forms import PrescriptionForm, PrescriptionItemFormSet


@group_required("DOCTOR")
def edit_for_ticket(request, ticket_id):
    """
    醫師針對某一張掛號票(VisitTicket) 開 / 編輯 處方籤喵
    URL 例如：/prescriptions/ticket/11/
    """

    print("=== [DEBUG] edit_for_ticket 進來了喵，method =", request.method)

    ticket = get_object_or_404(VisitTicket, id=ticket_id)

    # 確保登入的醫師就是這張 ticket 的醫師喵
    doctor = get_object_or_404(Doctor, user=request.user)
    if ticket.doctor != doctor:
        messages.error(request, "你不是這張掛號票的醫師喵，不能開處方。")
        return redirect("queues:doctor_panel")

    # 以「病人 + 醫師 + 日期」找或建立處方
    prescription, created = Prescription.objects.get_or_create(
        patient=ticket.patient,
        doctor=ticket.doctor,
        date=ticket.date,
        defaults={"status": Prescription.STATUS_DRAFT},
    )

    if request.method == "POST":
        print("=== [DEBUG] 收到 POST 了喵！POST 內容：", request.POST)

        form = PrescriptionForm(request.POST, instance=prescription)
        items = PrescriptionItemFormSet(request.POST, instance=prescription)

        print("=== [DEBUG] form.is_valid():", form.is_valid())
        print("=== [DEBUG] form.errors:", form.errors)
        print("=== [DEBUG] items.is_valid():", items.is_valid())
        print("=== [DEBUG] items.errors:", items.errors)
        print("=== [DEBUG] items.non_form_errors():", items.non_form_errors())

        if form.is_valid() and items.is_valid():
            # 先存主檔喵
            prescription = form.save(commit=False)
            prescription.patient = ticket.patient
            prescription.doctor = ticket.doctor
            prescription.date = ticket.date
            prescription.save()

            # 再存明細喵
            items.instance = prescription
            items.save()

            print("=== [DEBUG] 處方已成功儲存喵，準備 redirect ===")
            messages.success(request, "處方已儲存喵！")
            return redirect("queues:doctor_panel")

        else:
            print("=== [DEBUG] 表單驗證沒過喵，會回到同一頁並顯示錯誤 ===")
            messages.error(request, "表單有錯誤喵，請檢查紅色欄位。")
    else:
        # GET：第一次進來畫面喵
        form = PrescriptionForm(instance=prescription)
        items = PrescriptionItemFormSet(instance=prescription)

    context = {
        "ticket": ticket,
        "prescription": prescription,
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
    doctor = Doctor.objects.filter(user=request.user).first()
    if not doctor:
        messages.error(request, "找不到對應的醫師資料，請聯絡系統管理員喵。")
        return redirect("index")  # 或你想回去的頁面

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
    """
    病人自己的處方歷史列表喵
    """
    # 1. 找出目前登入的病人喵
    patient = get_object_or_404(Patient, chart_no=request.user.username)

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

@login_required
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



