from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from common.utils import group_required

from .models import Prescription, PrescriptionItem
from .forms import PrescriptionForm, PrescriptionItemFormSet

from inventory.models import StockTransaction
from queues.models import VisitTicket
from doctors.models import Doctor
from patients.models import Patient
from django.db import transaction


# ============================================================
#  藥局：今日待領藥列表 + 領藥動作
# ============================================================

@group_required("PHARMACY")  # 如果群組還沒設定好，暫時可以先拿掉 
def pharmacy_panel(request):
    """
    藥局領藥面板：顯示今天所有「待領藥」的處方 
    """
    today = timezone.localdate()

    prescriptions = (
        Prescription.objects
        .filter(
            date=today,
            status=Prescription.STATUS_FINAL,  
            pharmacy_status=Prescription.PHARMACY_PENDING,  # 只看待領藥 
        )
        .select_related("patient", "doctor__user")
        .prefetch_related("items__drug")
        .order_by("date", "id")
    )

    context = {
        "prescriptions": prescriptions,
        "today": today,
    }
    return render(request, "prescriptions/pharmacy_panel.html", context)


@group_required("PHARMACY")
@transaction.atomic
def dispense(request, pk):
    """
    藥局領藥頁面 + 領藥動作

    - GET：顯示處方明細、庫存狀態、按鈕
    - POST：完成領藥（扣庫存、寫異動、更新處方狀態）
    """
    prescription = get_object_or_404(
        Prescription.objects
        .select_related("patient", "doctor__user")
        .prefetch_related("items__drug"),
        pk=pk,
    )

    # 先把 items 抓出來，GET / POST 都會用到
    items = list(prescription.items.all())

    # 計算是否有任何一項庫存不足
    has_shortage = any(
        item.drug.stock_quantity < item.quantity
        for item in items
    )

    if request.method == "POST":
        action = request.POST.get("action", "complete")

        # 目前我們只處理完成領藥這個動作
        if action == "complete":
            # 再檢查一次庫存（避免有人趁你打開畫面時別處改了庫存）
            insufficient = []
            for item in items:
                drug = item.drug
                if drug.stock_quantity < item.quantity:
                    insufficient.append((drug, drug.stock_quantity, item.quantity))

            if insufficient:
                # 組錯誤訊息
                msg_lines = []
                for drug, stock, need in insufficient:
                    msg_lines.append(f"{drug.name} 庫存不足（現有 {stock}，需要 {need}）")
                messages.error(request, "無法完成領藥喵：\n" + "\n".join(msg_lines))
                # 回到藥局面板或留在同一頁都可以，先回面板喵
                return redirect("prescriptions:pharmacy_panel")

            # 2️⃣ 扣庫存 + 寫異動紀錄
            for item in items:
                drug = item.drug
                drug.stock_quantity -= item.quantity
                drug.save()

                StockTransaction.objects.create(
                    drug=drug,
                    change=-item.quantity,
                    reason="dispense",
                    prescription=prescription,
                    note=f"處方 #{prescription.id} 領藥",
                    # ⭐ 新增：記錄是誰動的這筆庫存
                    operator=request.user,
                )

            # 3️⃣ 更新處方的藥局狀態 & 領藥資訊
            prescription.pharmacy_status = Prescription.PHARMACY_DONE
            prescription.dispensed_at = timezone.now()

            # ⭐ 這裡寫進「領藥藥師」欄位（你 models 已經有 dispensed_by 了）
            prescription.dispensed_by = request.user

            # 如果你想順便保險一下，可把醫師端狀態也設成 FINAL
            if prescription.status != Prescription.STATUS_FINAL:
                prescription.status = Prescription.STATUS_FINAL

            prescription.save()

            messages.success(request, f"處方 #{prescription.id} 已完成領藥喵！")
            return redirect("prescriptions:pharmacy_panel")

        # 未來如果有其他 action（例如部分退藥），可以在這裡加 elif

        # 如果 action 不認得，就回到同一頁或面板
        messages.error(request, "未知的動作喵，請再試一次。")
        return redirect("prescriptions:pharmacy_panel")

    # ⭐⭐ 重點：GET 一定要 return 一個畫面，不能什麼都不回喵！
    context = {
        "prescription": prescription,
        "items": items,
        "has_shortage": has_shortage,
    }
    return render(request, "prescriptions/pharmacy_dispense.html", context)




# ============================================================
#  醫師：依掛號票開立 / 編輯處方
# ============================================================

@group_required("DOCTOR")
def edit_for_ticket(request, ticket_id):
    """
    醫師針對某一張掛號票 (VisitTicket) 開 / 編輯處方 
    URL 範例：/prescriptions/ticket/11/
    """
    print("=== [DEBUG] edit_for_ticket 進來了 ，method =", request.method)

    ticket = get_object_or_404(VisitTicket, id=ticket_id)

    # 確保登入的醫師就是這張 ticket 的醫師 
    doctor = get_object_or_404(Doctor, user=request.user)
    if ticket.doctor != doctor:
        messages.error(request, "你不是這張掛號票的醫師 ，不能開處方。")
        return redirect("queues:doctor_panel")

    # 以掛號（VisitTicket）為唯一依據，找或建立處方
    prescription, created = Prescription.objects.get_or_create(
        visit_ticket=ticket,
        defaults={
            "patient": ticket.patient,
            "doctor": ticket.doctor,
            "date": ticket.date,   # 或 ticket.created_at.date() 視你 model 的欄位而定
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
            # 先存主檔 
            prescription = form.save(commit=False)
            prescription.patient = ticket.patient
            prescription.doctor = ticket.doctor
            prescription.date = ticket.date

            prescription.status = Prescription.STATUS_FINAL

            prescription.save()

            # 再存明細 
            items.instance = prescription
            items.save()

            print("=== [DEBUG] 處方已成功儲存 ，準備 redirect ===")
            messages.success(request, "處方已儲存 ！")
            return redirect("queues:doctor_panel")
        else:
            print("=== [DEBUG] 表單驗證沒過 ，會回到同一頁並顯示錯誤 ===")
            messages.error(request, "表單有錯誤 ，請檢查紅色欄位。")

    else:
        # GET：第一次進來畫面 
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

    if prescription.pharmacy_status != Prescription.PHARMACY_PENDING:
        messages.error(request, "此處方已經由藥局處理，無法再修改喵。")
        return redirect("prescriptions:doctor_prescription_list")

    if request.method == "POST":
        form = PrescriptionForm(request.POST, instance=prescription)
        items = PrescriptionItemFormSet(request.POST, instance=prescription)

        if form.is_valid() and items.is_valid():
            # 先不要立即存，拿到物件
            prescription_obj = form.save(commit=False)

            # ⭐ 編輯完按儲存 → 視為「正式處方」
            prescription_obj.status = Prescription.STATUS_FINAL

            # 先存主處方，再存項目
            prescription_obj.save()
            items.instance = prescription_obj
            items.save()

            messages.success(request, "處方已更新並送出喵！")
            return redirect("prescriptions:doctor_prescription_list")
    else:
        form = PrescriptionForm(instance=prescription)
        items = PrescriptionItemFormSet(instance=prescription)

    context = {
        "prescription": prescription,
        "form": form,
        "items": items,
        "ticket": None,  # 這裡沒有 ticket，給 template 一個空的也沒關係
    }
    return render(request, "prescriptions/prescription_form.html", context)


@group_required("DOCTOR")
def doctor_prescription_list(request):
    """
    醫師查看自己開立過的所有處方 
    """
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


# ============================================================
#  病人：自己的處方列表 / 明細
# ============================================================

@login_required
@group_required("PATIENT")
def patient_prescription_list(request):
    """
    病人自己的處方歷史列表 （新版）
    """
    # 1. 找出目前登入的病人 （chart_no = username）
    patient = get_object_or_404(Patient, chart_no=request.user.username)

    # 2. 抓這個病人的所有處方 
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
    """
    病人查看單一處方明細 （新版 patient_ 開頭）
    """
    patient = get_object_or_404(Patient, user=request.user)

    prescription = get_object_or_404(
        Prescription.objects
        .select_related("doctor", "patient")
        .prefetch_related("items__drug"),
        pk=pk,
        patient=patient,   # 保證是自己的處方 
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
        # 不是病人帳號就不讓看 
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


# ============================================================
#  通用：處方明細（醫師 / 病人都可用）
# ============================================================

@login_required
def prescription_detail(request, pk):
    """
    醫師 / 病人查看處方明細（唯讀） 
    """
    prescription = get_object_or_404(
        Prescription.objects
        .select_related("patient", "doctor", "doctor__user")
        .prefetch_related("items__drug"),
        pk=pk,
    )

    user = request.user

    # 權限檢查 ：只有該處方的醫師或病人可以看
    can_see = False
    if hasattr(user, "doctor") and user.doctor == prescription.doctor:
        can_see = True
    if hasattr(user, "patient") and user.patient == prescription.patient:
        can_see = True

    if not can_see:
        return HttpResponseForbidden("你沒有權限查看這張處方 ")

    context = {
        "prescription": prescription,
    }
    return render(request, "prescriptions/prescription_detail.html", context)

@group_required("PHARMACY")
@transaction.atomic
def cancel_or_return_prescription(request, pk):
    prescription = get_object_or_404(
        Prescription.objects.prefetch_related("items__drug"),
        pk=pk
    )

    # 不能對已作廢的處方做動作
    if prescription.pharmacy_status == Prescription.PHARMACY_CANCELLED:
        messages.warning(request, "這張處方已經作廢過喵。")
        return redirect("prescriptions:pharmacy_panel")

    # POST 才能操作
    if request.method == "POST":

        # 1️⃣ 情境一：還沒領藥 → 作廢（不動庫存）
        if prescription.pharmacy_status == Prescription.PHARMACY_PENDING:
            prescription.pharmacy_status = Prescription.PHARMACY_CANCELLED
            prescription.save()
            messages.success(request, f"處方 #{prescription.id} 已作廢喵！")
            return redirect("prescriptions:pharmacy_panel")

        # 2️⃣ 情境二：已領藥 → 退藥（加回庫存）
        if prescription.pharmacy_status == Prescription.PHARMACY_DONE:

            for item in prescription.items.all():
                drug = item.drug

                # 加回庫存
                drug.stock_quantity += item.quantity
                drug.save()

                # 建立退藥異動
                StockTransaction.objects.create(
                    drug=drug,
                    change=+item.quantity,
                    reason="return",
                    prescription=prescription,
                    note=f"處方 #{prescription.id} 退藥",
                    performed_by=request.user,
                )

            prescription.pharmacy_status = Prescription.PHARMACY_CANCELLED
            prescription.save()

            messages.success(request, f"處方 #{prescription.id} 已退藥並作廢喵！")
            return redirect("prescriptions:pharmacy_panel")

    # GET → 顯示一個簡單確認畫面（你可自己做）
    return render(request, "prescriptions/cancel_or_return_confirm.html", {
        "prescription": prescription,
    })

