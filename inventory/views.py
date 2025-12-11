from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum  
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required, permission_required

from django.contrib.auth import get_user_model
from django.urls import reverse

from inventory.utils import adjust_stock
from datetime import timedelta
from django.utils import timezone

from .forms import DrugForm, StockAdjustForm, StockBatchForm
from common.utils import group_required
from .models import Drug, StockBatch, StockTransaction
from django.core.paginator import Paginator 

# ------------------------------
# 儀表板
# ------------------------------
@group_required("PHARMACY")
def dashboard(request):
    # 只抓啟用中的藥品 
    drugs = Drug.objects.filter(is_active=True).order_by("name")

    # 1️⃣ 總藥品品項數
    total_drugs = drugs.count()

    # 2️⃣ 總庫存數量（所有藥的 stock_quantity 加總）
    total_stock_quantity = drugs.aggregate(
        total=Sum("stock_quantity")
    )["total"] or 0

    # 3️⃣ 低庫存藥品（庫存 <= 安全存量）
    low_stock_drugs = drugs.filter(
        stock_quantity__lte=F("reorder_level"),
    )
    low_stock_count = low_stock_drugs.count()

    # 4️⃣ 最近庫存異動紀錄
    recent_transactions = (
        StockTransaction.objects
        .select_related("drug")
        .order_by("-created_at")[:10]
    )

    return render(request, "inventory/dashboard.html", {
        "total_drugs": total_drugs,
        "total_stock_quantity": total_stock_quantity,
        "low_stock_count": low_stock_count,
        "low_stock_drugs": low_stock_drugs,
        "recent_transactions": recent_transactions,
    })


# ------------------------------
# 藥品列表
# ------------------------------
@login_required
def drug_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")          # active / inactive / 空字串
    stock_filter = request.GET.get("stock", "")     # low / ok / 空字串

    drugs = Drug.objects.all().order_by("name")

    # 關鍵字搜尋：名字 / 學名 / 劑型
    if query:
        drugs = drugs.filter(
            Q(name__icontains=query) |
            Q(generic_name__icontains=query) |
            Q(form__icontains=query)
        )

    # 狀態篩選
    if status == "active":
        drugs = drugs.filter(is_active=True)
    elif status == "inactive":
        drugs = drugs.filter(is_active=False)

    # 庫存篩選
    if stock_filter == "low":
        # 只看低庫存（啟用 + 庫存 <= 安全存量）
        drugs = drugs.filter(is_active=True, stock_quantity__lte=F("reorder_level"))
    elif stock_filter == "ok":
        # 排除低庫存
        drugs = drugs.exclude(is_active=True, stock_quantity__lte=F("reorder_level"))

    # 分頁：每頁 20 筆（你可以自己改）
    paginator = Paginator(drugs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "inventory/drug_list.html",
        {
            "drugs": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "status": status,
            "stock_filter": stock_filter,
        },
    )



# ------------------------------
# 新增藥品（使用 drug_create.html）
# ------------------------------
@login_required
@permission_required("inventory.add_drug", raise_exception=True)
def drug_create(request):
    if request.method == "POST":
        form = DrugForm(request.POST)
        if form.is_valid():
            drug = form.save()

            # 如果有初始庫存 → 建立異動紀錄
            if drug.stock_quantity > 0:
                StockTransaction.objects.create(
                    drug=drug,
                    change=drug.stock_quantity,
                    reason="initial",
                    note="新增藥品初始庫存",
                )

            messages.success(request, "藥品新增成功 ！")
            return redirect("inventory:drug_list")

    else:
        form = DrugForm()

    return render(request, "inventory/drug_create.html", {"form": form})


# ------------------------------
# 編輯藥品（使用 drug_edit.html）
# ------------------------------
@group_required("PHARMACY")
def edit_drug(request, pk):
    drug = get_object_or_404(Drug, pk=pk)

    if request.method == "POST":
        form = DrugForm(request.POST, instance=drug)
        if form.is_valid():
            form.save()
            messages.success(request, f"已成功更新 {drug.name}  ！")
            return redirect("inventory:drug_list")
    else:
        form = DrugForm(instance=drug)

    return render(request, "inventory/drug_edit.html", {
        "form": form,
        "drug": drug,
    })


# ------------------------------
# 庫存異動：入庫 / 出庫 / 調整
# ------------------------------
@group_required("PHARMACY")
@transaction.atomic
def stock_adjust(request, pk):
    """
    單一藥品庫存調整：
    - 使用 StockAdjustForm 收集「原因 / 數量 / 備註」
    - 實際異動交給 inventory.utils.adjust_stock()
    """
    drug = get_object_or_404(Drug, pk=pk)

    if request.method == "POST":
        form = StockAdjustForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data["reason"]   # purchase / dispense / return / adjust
            qty = form.cleaned_data["quantity"]    # 正整數
            note = form.cleaned_data["note"]

            # 依照原因決定是加還是減
            change = qty
            if reason in ("dispense", "adjust") and qty > 0:
                # 發藥或調整（扣庫存）：變成負數
                change = -qty

            try:
                # ✨ 統一透過 adjust_stock 處理：
                # - 檢查庫存是否不足
                # - 寫入 StockTransaction
                # - 更新 drug.stock_quantity
                adjust_stock(
                    drug=drug,
                    change=change,
                    reason=reason,
                    note=note,
                    prescription=None,
                    operator=request.user,   # ✅ 記錄調整人
                )
            except ValueError as e:
                # 例如：庫存不足會在 adjust_stock 丟 ValueError
                messages.error(request, str(e))
            else:
                # 重新讀取最新庫存
                drug.refresh_from_db()
                messages.success(
                    request,
                    f"已調整 {drug.name} 庫存（變動 {change}，目前庫存 {drug.stock_quantity}） ",
                )
                return redirect("inventory:drug_list")
        else:
            # 先印出錯誤，方便你看 console 除錯
            print("StockAdjustForm errors:", form.errors)
    else:
        form = StockAdjustForm()

    # 最近 20 筆該藥品的異動紀錄
    logs = (
        StockTransaction.objects.filter(drug=drug)
        .order_by("-created_at")[:20]
    )

    return render(
        request,
        "inventory/stock_adjust.html",
        {
            "drug": drug,
            "form": form,
            "logs": logs,
        },
    )

# ------------------------------
# 全部異動紀錄（可指定藥品 / 搜尋 / 過濾 / 分頁）
# ------------------------------
# ------------------------------
# 全部異動紀錄（可指定藥品 / 搜尋 / 過濾 / 分頁）
# ------------------------------
@group_required("PHARMACY")
def stock_history(request):
    # 🔙 先決定 back_url
    back_url = request.GET.get("back")
    if not back_url:
        back_url = request.META.get("HTTP_REFERER") or reverse("inventory:dashboard")

    # 基本 queryset
    qs = (
        StockTransaction.objects
        .select_related("drug", "operator", "prescription")
        .order_by("-created_at")
    )

    # 0️⃣ 指定單一藥品 ?drug=xx
    drug_id = request.GET.get("drug")
    selected_drug = None
    if drug_id:
        qs = qs.filter(drug_id=drug_id)
        selected_drug = Drug.objects.filter(pk=drug_id).first()

    # 1️⃣ 搜尋藥名（只在「全部藥品模式」有意義）
    q_drug = request.GET.get("q_drug") or ""
    if q_drug:
        qs = qs.filter(drug__name__icontains=q_drug)

    # 2️⃣ 搜尋 By（operator：username / first_name / last_name）
    q_operator = request.GET.get("q_operator") or ""
    if q_operator:
        qs = qs.filter(
            Q(operator__username__icontains=q_operator)
            | Q(operator__first_name__icontains=q_operator)
            | Q(operator__last_name__icontains=q_operator)
        )

    # 3️⃣ 日期區間過濾（created_at 的日期）
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # 4️⃣ 類別過濾（進貨 / 發藥 / 調整 / 退藥）
    reason = request.GET.get("reason") or ""
    if reason:
        qs = qs.filter(reason=reason)

    # ⭐ 在分頁前先算 summary
    total_count = qs.count()

    summary = qs.aggregate(
        total_in=Sum("change", filter=Q(change__gt=0)),
        total_out=Sum("change", filter=Q(change__lt=0)),
    )
    total_in = summary["total_in"] or 0
    raw_total_out = summary["total_out"] or 0   # 這通常是負數
    net_change = total_in + raw_total_out

    # 5️⃣ 分頁（每頁 20 筆）
    paginator = Paginator(qs, 20)
    page = request.GET.get("page")
    transactions = paginator.get_page(page)

    context = {
        "transactions": transactions,
        "selected_drug": selected_drug,
        "drug_id": drug_id,
        "back_url": back_url,

        # 把目前的搜尋條件都塞回去 template
        "q_drug": q_drug,
        "q_operator": q_operator,
        "date_from": date_from,
        "date_to": date_to,
        "reason": reason,

        # ⭐ 給 template 顯示 summary 用
        "total_count": total_count,
        "total_in": total_in,
        "total_out": abs(raw_total_out),  # 顯示成正數
        "net_change": net_change,
    }
    return render(request, "inventory/stock_history.html", context)


# ------------------------------
# 單一藥品異動紀錄
# ------------------------------
@login_required
def stock_history_drug(request, drug_id):
    # 重導向到新版統一的 Stock History 頁面
    return redirect(f"/inventory/history/?drug={drug_id}")



@group_required("PHARMACY")  # 只有藥局群組可以看這個頁面喵（沒設定群組就先暫時拿掉）
def expiry_dashboard(request):
    """
    藥品效期管理儀表板：
    - 列出所有「已過期」且尚有庫存的批次
    - 列出「N 天內到期」且尚有庫存的批次
    """
    today = timezone.localdate()
    warning_days = 30  # 你可以改成 60 / 90 之類喵

    # 🔴 已過期（expiry_date < today 且 quantity > 0）
    expired_batches = (
        StockBatch.objects
        .select_related("drug")
        .filter(
            expiry_date__lt=today,
            quantity__gt=0,
        )
        .order_by("expiry_date", "drug__name", "batch_no")
    )

    # 🟡 即將於 N 天內到期（today <= expiry_date <= today + N）
    near_expiry_batches = (
        StockBatch.objects
        .select_related("drug")
        .filter(
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=warning_days),
            quantity__gt=0,
        )
        .order_by("expiry_date", "drug__name", "batch_no")
    )

    context = {
        "today": today,
        "warning_days": warning_days,
        "expired_batches": expired_batches,
        "near_expiry_batches": near_expiry_batches,
    }
    return render(request, "inventory/expiry_dashboard.html", context)

@group_required("PHARMACY")
@transaction.atomic
def stock_in(request, drug_id):
    drug = get_object_or_404(Drug, pk=drug_id)

    if request.method == "POST":
        form = StockBatchForm(request.POST)
        if form.is_valid():
            batch = form.save(commit=False)
            batch.drug = drug
            batch.save()

            # 🔥 批次總和 → 寫回 Drug.stock_quantity
            total_qty = drug.batches.aggregate(total=Sum("quantity"))["total"] or 0
            drug.stock_quantity = total_qty
            drug.save(update_fields=["stock_quantity"])

            # 建立異動紀錄
            StockTransaction.objects.create(
                drug=drug,
                change=batch.quantity,
                reason="purchase",
                note=f"進貨批號：{batch.batch_no}, 效期：{batch.expiry_date}",
                operator=request.user,
            )

            messages.success(request, f"成功進貨 {batch.quantity} 喵！")
            return redirect("inventory:drug_list")
    else:
        form = StockBatchForm()

    return render(request, "inventory/stock_in.html", {"drug": drug, "form": form})