import csv
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum  
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required, permission_required

from django.urls import reverse

from inventory.utils import adjust_stock
from datetime import timedelta
from django.utils import timezone

from .forms import DrugForm, StockAdjustForm, StockBatchForm
from common.utils import group_required
from .models import Drug, StockBatch, StockTransaction
from django.core.paginator import Paginator 
from inventory.utils import stock_in as stock_in_utils
from inventory.utils import quarantine_batch, unquarantine_batch, destroy_batch
from django.http import HttpResponse

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
    return redirect(f"{reverse('inventory:stock_history')}?drug={drug_id}")




@group_required("PHARMACY")
def expiry_dashboard(request):
    """
    藥品效期管理儀表板：
    - 已過期（不可發藥）
    - N 天內到期（提醒）
    - 隔離批次（不可發藥，待藥師處理）
    """
    today = timezone.localdate()
    warning_days = 30
    warn_date = today + timedelta(days=warning_days)

    expired_batches = (
        StockBatch.objects
        .select_related("drug")
        .filter(
            status=StockBatch.STATUS_NORMAL,
            expiry_date__lt=today,
            quantity__gt=0,
        )
        .order_by("expiry_date", "drug__name", "batch_no")
    )

    near_expiry_batches = (
        StockBatch.objects
        .select_related("drug")
        .filter(
            status=StockBatch.STATUS_NORMAL,
            expiry_date__gte=today,
            expiry_date__lte=warn_date,
            quantity__gt=0,
        )
        .order_by("expiry_date", "drug__name", "batch_no")
    )

    quarantined_batches = (
        StockBatch.objects
        .select_related("drug")
        .filter(
            status=StockBatch.STATUS_QUARANTINE,
            quantity__gt=0,
        )
        .order_by("expiry_date", "drug__name", "batch_no")
    )

    q = (request.GET.get("q") or "").strip()
    search_batches = StockBatch.objects.none()
    if q:
        search_batches = (
            StockBatch.objects
            .select_related("drug")
            .filter(quantity__gt=0)
            .filter(
                Q(drug__code__icontains=q) |
                Q(drug__name__icontains=q) |
                Q(batch_no__icontains=q)
            )
            .order_by("expiry_date", "id")[:50]
        )

    expired_count = expired_batches.count()
    near_expiry_count = near_expiry_batches.count()
    quarantine_count = quarantined_batches.count()


    return render(request, "inventory/expiry_dashboard.html", {
        "today": today,
        "warning_days": warning_days,
        "expired_batches": expired_batches,
        "near_expiry_batches": near_expiry_batches,
        "quarantined_batches": quarantined_batches,

        "expired_count": expired_count,
        "near_expiry_count": near_expiry_count,
        "quarantine_count": quarantine_count,

        "q": q,
        "search_batches": search_batches,
    })


@group_required("PHARMACY")
@transaction.atomic
def stock_in(request, drug_id):
    drug = get_object_or_404(Drug, pk=drug_id)

    if request.method == "POST":
        form = StockBatchForm(request.POST)
        if form.is_valid():
            expiry_date = form.cleaned_data["expiry_date"]
            quantity = form.cleaned_data["quantity"]

            # 如果你表單有 note / supplier_batch_no 就拿出來，沒有也沒關係
            note = form.cleaned_data.get("note", "") if hasattr(form, "cleaned_data") else ""

            try:
                batch = stock_in_utils(
                    drug=drug,
                    quantity=quantity,
                    expiry_date=expiry_date,
                    operator=request.user,
                    note=note,
                )
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("inventory:stock_in", drug_id=drug.id)

            messages.success(request, f"成功進貨 {batch.quantity}  ！（批號 {batch.batch_no}）")
            return redirect("inventory:drug_list")
    else:
        form = StockBatchForm()

    return render(request, "inventory/stock_in.html", {"drug": drug, "form": form})


# inventory/views.py

@group_required("PHARMACY")
@transaction.atomic
def batch_quarantine(request, batch_id):
    if request.method != "POST":
        return redirect("inventory:expiry_dashboard")

    batch = get_object_or_404(StockBatch.objects.select_for_update(), pk=batch_id)

    if batch.quantity <= 0:
        messages.warning(request, "此批次已無庫存，不需隔離 。")
        return redirect("inventory:expiry_dashboard")

    reason = (request.POST.get("reason") or "").strip()
    note = (request.POST.get("note") or "").strip()

    if not reason or not note:
        messages.error(request, "隔離需要選原因，且備註必填 。")
        return redirect("inventory:expiry_dashboard")

    quarantine_batch(
        batch,
        operator=request.user,
        reason=reason,
        note=note,
    )

    messages.success(request, f"已將批次 {batch.batch_no or '-'} 設為隔離 。")
    return redirect("inventory:quarantine_dashboard")






@group_required("PHARMACY")
@transaction.atomic
def batch_destroy(request, batch_id):
    if request.method != "POST":
        return redirect("inventory:expiry_dashboard")

    batch = get_object_or_404(StockBatch.objects.select_for_update(), pk=batch_id)

    qty_str = (request.POST.get("quantity") or "").strip()
    qty = None
    if qty_str:
        if not qty_str.isdigit():
            messages.error(request, "報廢數量必須是整數 。")
            return redirect("inventory:expiry_dashboard")
        qty = int(qty_str)

    reason = (request.POST.get("reason") or "").strip() or "藥師判斷報廢/銷毀"

    try:
        destroy_batch(batch, quantity=qty, operator=request.user, note=reason)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("inventory:expiry_dashboard")

    messages.success(request, f"已處理批次 {batch.batch_no or '-'} 的報廢/銷毀 。")
    return redirect("inventory:expiry_dashboard")


@group_required("PHARMACY")
def quarantine_dashboard(request):
    batches = (
        StockBatch.objects
        .select_related("drug")
        .filter(status=StockBatch.STATUS_QUARANTINE, quantity__gt=0)
        .order_by("expiry_date", "drug__name", "batch_no")
    )
    return render(request, "inventory/quarantine_dashboard.html", {"batches": batches})


@group_required("PHARMACY")
@transaction.atomic
def batch_unquarantine(request, batch_id):
    if request.method != "POST":
        return redirect("inventory:quarantine_dashboard")

    batch = get_object_or_404(StockBatch.objects.select_for_update(), pk=batch_id)

    try:
        unquarantine_batch(batch, operator=request.user, note="藥師解除隔離")
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("inventory:quarantine_dashboard")

    messages.success(request, "已解除隔離，批次已回到正常庫存 。")
    return redirect("inventory:quarantine_dashboard")

@group_required("PHARMACY")
def stock_history_export_csv(request):
    qs = (
        StockTransaction.objects
        .select_related("drug", "batch", "operator", "prescription")
        .order_by("-created_at")
    )

    drug_id = (request.GET.get("drug") or "").strip()
    reason = (request.GET.get("reason") or "").strip()
    q_operator = (request.GET.get("q_operator") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    q_drug = (request.GET.get("q_drug") or "").strip()

    if drug_id:
        qs = qs.filter(drug_id=drug_id)
    if reason:
        qs = qs.filter(reason=reason)
    if q_drug:
        qs = qs.filter(drug__name__icontains=q_drug)
    if q_operator:
        qs = qs.filter(
            Q(operator__username__icontains=q_operator)
            | Q(operator__first_name__icontains=q_operator)
            | Q(operator__last_name__icontains=q_operator)
        )
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="stock_history.csv"'
    resp.write("\ufeff")  # Excel 友善 BOM  

    w = csv.writer(resp)
    w.writerow([
        "DateTime",
        "DrugCode",
        "DrugName",
        "BatchNo",
        "ExpiryDate",
        "Reason",
        "Change",
        "Rx",
        "Operator",
        "Note",
    ])

    for tx in qs:
        w.writerow([
            tx.created_at.strftime("%Y-%m-%d %H:%M"),
            tx.drug.code if tx.drug else "",
            tx.drug.name if tx.drug else "",
            (tx.batch.batch_no if tx.batch else ""),
            (tx.batch.expiry_date.strftime("%Y-%m-%d") if tx.batch and tx.batch.expiry_date else ""),
            tx.reason,
            tx.change,
            (tx.prescription.id if tx.prescription else ""),
            (tx.operator.get_username() if tx.operator else ""),
            tx.note or "",
        ])

    return resp

