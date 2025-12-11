# C:\project\hospitalsys\inventory\utils.py

from django.utils import timezone
from django.db import transaction, models
from .models import Drug, StockBatch, StockTransaction
from django.db.models import Sum


@transaction.atomic
def adjust_stock(
    drug: Drug,
    change: int,
    reason: str,
    note: str = "",
    prescription=None,
    operator=None,
):
    """
    通用庫存調整工具：
    - change: 正數 = 增加庫存 / 負數 = 扣庫存
    - reason: 'purchase' / 'dispense' / 'return' / 'adjust'
    - note  : 備註
    """
    new_stock = drug.stock_quantity + change
    if new_stock < 0:
        raise ValueError(f"{drug.name} 庫存不足，無法扣除 {abs(change)} 喵")

    drug.stock_quantity = new_stock
    drug.save()

    StockTransaction.objects.create(
        drug=drug,
        change=change,
        reason=reason,
        note=note,
        prescription=prescription,
        operator=operator,
    )
    return drug

@transaction.atomic
def use_drug(drug: Drug, quantity: int) -> bool:
    """
    依「最早到期優先」從未過期批次扣庫存喵。
    回傳：
      True  = 成功全部扣完
      False = 庫存不足（或全部是過期批次）
    """
    if quantity <= 0:
        return True  # 要扣 0 其實算成功喵

    today = timezone.localdate()

    # 只看「尚未過期、數量 > 0」的批次，照效期先後排喵
    batches = (
        StockBatch.objects
        .select_for_update()
        .filter(drug=drug, expiry_date__gte=today, quantity__gt=0)
        .order_by("expiry_date", "id")
    )

    remaining = quantity

    for batch in batches:
        if remaining <= 0:
            break

        if batch.quantity > remaining:
            # 這一批就夠扣喵
            used = remaining
            batch.quantity -= used
            batch.save(update_fields=["quantity"])

            StockTransaction.objects.create(
                drug=drug,
                change=-used,
                reason="dispense",
                note=f"從批號 {batch.batch_no or '-'} 扣庫存",
            )

            remaining = 0

        else:
            # 這一批不夠，全部扣光喵
            used = batch.quantity
            batch.quantity = 0
            batch.save(update_fields=["quantity"])

            StockTransaction.objects.create(
                drug=drug,
                change=-used,
                reason="dispense",
                note=f"從批號 {batch.batch_no or '-'} 扣庫存",
            )

            remaining -= used

    # 用批次扣完後，統一重算 Drug 的總庫存喵
    total = (
        StockBatch.objects
        .filter(drug=drug, quantity__gt=0)
        .aggregate(total=models.Sum("quantity"))
    )["total"] or 0

    drug.stock_quantity = total
    drug.save(update_fields=["stock_quantity"])

    # 如果還有扣不完的，代表庫存不足喵
    return remaining == 0

def use_drug_from_prescription_item(item, operator=None, prescription=None):
    """
    舊版程式用的 Helper：從單一處方明細扣庫存喵。

    參數：
    - item: prescriptions.PrescriptionItem 實例
    - operator: request.user（藥師帳號），可為 None
    - prescription: 可選，若有傳進來就優先使用，沒傳就用 item.prescription 喵
    """
    # 如果上面已經有 import Sum，就可以刪掉這行；保險起見留著也不會壞喵
    from django.db.models import Sum

    drug = item.drug
    qty = item.quantity or 0
    if qty <= 0:
        return

    # 如果呼叫方有傳 prescription=... 就用那個，否則 fallback 到 item.prescription 喵
    presc = prescription or getattr(item, "prescription", None)

    today = timezone.localdate()
    remain = qty

    # 只用「未過期、有庫存」的批次，而且先用最早到期的（FEFO）喵
    batches = (
        StockBatch.objects
        .select_for_update()
        .filter(drug=drug, expiry_date__gte=today, quantity__gt=0)
        .order_by("expiry_date", "id")
    )

    with transaction.atomic():
        for batch in batches:
            if remain <= 0:
                break

            take = min(batch.quantity, remain)
            if take <= 0:
                continue

            # 扣掉該批次庫存喵
            batch.quantity -= take
            batch.save(update_fields=["quantity"])

            # 記錄庫存異動喵
            StockTransaction.objects.create(
                drug=drug,
                change=-take,
                reason="dispense",
                prescription=presc,
                operator=operator,
                note=f"處方明細 #{item.id} 扣庫存（批號 {batch.batch_no or '-'}）",
            )

            remain -= take

        # 重新計算 Drug 總庫存（全部批次加總）喵
        total = (
            StockBatch.objects
            .filter(drug=drug)
            .aggregate(total=Sum("quantity"))
        )["total"] or 0

        drug.stock_quantity = total
        drug.save(update_fields=["stock_quantity"])



@transaction.atomic
def stock_in(drug: Drug, quantity: int, expiry_date, batch_no="", operator=None, note=""):
    """
    進貨 / 增加庫存：
    - 建立或更新某一批次的 quantity
    - 同時更新 Drug.stock_quantity
    - 紀錄 StockTransaction（原因：purchase）
    """
    if quantity <= 0:
        raise ValueError("quantity 必須是正數喵")

    # 1. 找「同藥品 + 同效期 + 同批號」的批次，如果沒有就新建
    batch, created = StockBatch.objects.get_or_create(
        drug=drug,
        expiry_date=expiry_date,
        batch_no=batch_no or "",
        defaults={"quantity": quantity},
    )

    if not created:
        batch.quantity += quantity
        batch.save(update_fields=["quantity"])

    # 2. 重算 Drug.stock_quantity（用所有批次相加）
    total = (
        StockBatch.objects
        .filter(drug=drug)
        .aggregate(total=models.Sum("quantity"))
    )["total"] or 0

    drug.stock_quantity = total
    drug.save(update_fields=["stock_quantity"])

    # 3. 紀錄異動
    StockTransaction.objects.create(
        drug=drug,
        # 如果你有 batch / type 欄位，這裡一起寫喵：
        # batch=batch,
        change=quantity,
        reason="purchase",
        note=note,
        operator=operator,
    )

    return batch

def refresh_stock_quantity(drug: Drug):
    """重新整理 Drug.stock_quantity，從所有批次加總喵"""
    total = drug.batches.aggregate(total=Sum("quantity"))["total"] or 0
    drug.stock_quantity = total
    drug.save(update_fields=["stock_quantity"])
