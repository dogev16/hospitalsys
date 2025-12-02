from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required, permission_required

from .forms import DrugForm, StockAdjustForm
from common.utils import group_required
from .models import Drug, StockTransaction


# ------------------------------
# 儀表板
# ------------------------------
@group_required("PHARMACY")
def dashboard(request):
    drugs = Drug.objects.all().order_by("name")
    low_stock = drugs.filter(
        is_active=True,
        stock_quantity__lte=F("reorder_level"),
    )

    return render(request, "inventory/dashboard.html", {
        "drugs": drugs,
        "low_stock": low_stock,
    })


# ------------------------------
# 藥品列表
# ------------------------------
@login_required
def drug_list(request):
    query = request.GET.get("q", "")
    drugs = Drug.objects.all()

    if query:
        drugs = drugs.filter(
            Q(name__icontains=query) |
            Q(generic_name__icontains=query) |
            Q(form__icontains=query)
        )

    return render(request, "inventory/drug_list.html", {
        "drugs": drugs,
        "query": query,
    })


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

            messages.success(request, "藥品新增成功喵！")
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
            messages.success(request, f"已成功更新 {drug.name} 喵！")
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
    drug = get_object_or_404(Drug, pk=pk)

    if request.method == "POST":
        form = StockAdjustForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data["reason"]   # purchase / dispense / adjust
            qty = form.cleaned_data["quantity"]    # ✅ 名字跟 forms.StockAdjustForm 一致
            note = form.cleaned_data["note"]

            # 依照原因決定是加還是減
            change = qty
            if reason in ("dispense", "adjust") and qty > 0:
                # 發藥或調整（扣庫存）：變成負數
                change = -qty

            new_stock = drug.stock_quantity + change
            if new_stock < 0:
                messages.error(request, "庫存不足，無法扣除這麼多喵")
            else:
                # 更新藥品庫存
                drug.stock_quantity = new_stock
                drug.save()

                # 建立異動紀錄
                StockTransaction.objects.create(
                    drug=drug,
                    change=change,
                    reason=reason,
                    note=note,
                )

                messages.success(
                    request,
                    f"已調整 {drug.name} 庫存（變動 {change}，目前庫存 {new_stock}）喵",
                )
                return redirect("inventory:drug_list")
        else:
            # 先印出錯誤，方便你看 console 除錯喵
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
# 全部異動紀錄
# ------------------------------
@group_required("PHARMACY")
def stock_history(request):
    transactions = StockTransaction.objects.select_related("drug").order_by("-created_at")
    return render(request, "inventory/stock_history.html", {"transactions": transactions})


# ------------------------------
# 單一藥品異動紀錄
# ------------------------------
@login_required
def stock_history_drug(request, drug_id):
    drug = get_object_or_404(Drug, pk=drug_id)
    transactions = StockTransaction.objects.filter(drug=drug).order_by("-created_at")

    return render(request, "inventory/stock_history_drug.html", {
        "drug": drug,
        "transactions": transactions,
    })
