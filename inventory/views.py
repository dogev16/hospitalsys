from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django import forms

from common.utils import group_required   # ✅ 統一從 common.utils 拿 decorator
from .models import Drug, StockTransaction
from .utils import adjust_stock
from django.db.models import F


# ------------------------------
# 內部用的簡單 ModelForm
# ------------------------------
class DrugForm(forms.ModelForm):
    class Meta:
        model = Drug
        fields = [
            "code",
            "name",
            "generic_name",
            "form",
            "strength",
            "unit",
            "stock_quantity",
            "reorder_level",
            "is_active",
        ]


# ------------------------------
# 儀表板（簡單版本）
# ------------------------------
@group_required("PHARMACY")
def dashboard(request):
    """
    藥局儀表板：
    - 顯示所有藥品
    - 顯示低庫存清單
    """
    drugs = Drug.objects.all().order_by("name")
    low_stock = drugs.filter(stock_quantity__lte=F("reorder_level"))


    context = {
        "drugs": drugs,
        "low_stock": low_stock,
    }
    return render(request, "inventory/dashboard.html", context)


# ------------------------------
# 藥品列表
# ------------------------------
@group_required("PHARMACY")
def drug_list(request):
    drugs = Drug.objects.all().order_by("name")
    return render(request, "inventory/drug_list.html", {"drugs": drugs})


# ------------------------------
# 新增藥品
# ------------------------------
@group_required("PHARMACY")
def new_drug(request):
    if request.method == "POST":
        form = DrugForm(request.POST)
        if form.is_valid():
            drug = form.save()
            messages.success(request, f"已新增藥品：{drug.name} 喵")
            return redirect("inventory:drug_list")
    else:
        form = DrugForm()

    return render(request, "inventory/drug_form.html", {"form": form, "mode": "new"})


# ------------------------------
# 編輯藥品
# ------------------------------
@group_required("PHARMACY")
def edit_drug(request, pk):
    drug = get_object_or_404(Drug, pk=pk)

    if request.method == "POST":
        form = DrugForm(request.POST, instance=drug)
        if form.is_valid():
            form.save()
            messages.success(request, f"已更新藥品：{drug.name} 喵")
            return redirect("inventory:drug_list")
    else:
        form = DrugForm(instance=drug)

    return render(
        request,
        "inventory/drug_form.html",
        {
            "form": form,
            "mode": "edit",
            "drug": drug,
        },
    )


# ------------------------------
# 調整庫存（入庫 / 出庫 / 調整）
# ------------------------------
class StockAdjustForm(forms.Form):
    TYPE_CHOICES = [
        ("IN", "入庫 / 採購"),
        ("OUT", "出庫 / 調劑"),
        ("ADJ", "庫存調整"),
    ]

    ttype = forms.ChoiceField(label="異動類型", choices=TYPE_CHOICES)
    quantity = forms.IntegerField(label="異動數量")
    reason = forms.CharField(label="原因 / 備註", max_length=200, required=False)


@group_required("PHARMACY")
def adjust_stock_view(request, drug_id):
    drug = get_object_or_404(Drug, pk=drug_id)

    if request.method == "POST":
        form = StockAdjustForm(request.POST)
        if form.is_valid():
            ttype = form.cleaned_data["ttype"]
            qty = form.cleaned_data["quantity"]
            reason = form.cleaned_data["reason"]

            # IN / OUT / ADJ：統一走 adjust_stock
            try:
                adjust_stock(drug, qty if ttype != "OUT" else -abs(qty), ttype, reason)
            except ValueError as e:
                messages.error(request, f"庫存調整失敗：{e} 喵")
            else:
                messages.success(
                    request,
                    f"已調整 {drug.name} 庫存（{ttype}：{qty}）喵",
                )
                return redirect("inventory:drug_list")
    else:
        form = StockAdjustForm()

    # 顯示最近幾筆異動紀錄
    recent_logs = StockTransaction.objects.filter(drug=drug).order_by("-created_at")[:20]

    return render(
        request,
        "inventory/adjust_stock.html",
        {
            "drug": drug,
            "form": form,
            "logs": recent_logs,
        },
    )
