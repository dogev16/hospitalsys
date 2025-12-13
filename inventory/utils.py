# C:\project\hospitalsys\inventory\utils.py

from __future__ import annotations

from datetime import timedelta
from django.utils import timezone
from django.db import transaction, models
from django.db.models import Sum

from .models import Drug, StockBatch, StockTransaction


def refresh_stock_quantity(drug: Drug) -> int:
    """重新整理 Drug.stock_quantity（只加總未過期或全部？這裡用全部批次 quantity 總和） """
    total = drug.batches.aggregate(total=Sum("quantity"))["total"] or 0
    drug.stock_quantity = total
    drug.save(update_fields=["stock_quantity"])
    return total


# ---------------------------------------------------------------------
# ✅ 保留：舊系統/其他模組可能還有 import adjust_stock
#   但在「完全批次庫存」模式下，建議不要再用它做進貨/發藥，
#   改用 stock_in / use_drug_from_prescription_item / adjust_batch_stock  
# ---------------------------------------------------------------------
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
    舊版「以 Drug.stock_quantity 為主」的調整工具。
    為了相容保留；批次模式下你應該改用 adjust_batch_stock  
    """
    new_stock = (drug.stock_quantity or 0) + change
    if new_stock < 0:
        raise ValueError(f"{drug.name} 庫存不足，無法扣除 {abs(change)}  ")

    drug.stock_quantity = new_stock
    drug.save(update_fields=["stock_quantity"])

    StockTransaction.objects.create(
        drug=drug,
        batch=None,
        change=change,
        reason=reason,
        note=note,
        prescription=prescription,
        operator=operator,
    )
    return drug


@transaction.atomic
def adjust_batch_stock(
    batch: StockBatch,
    change: int,
    reason: str = "adjust",
    note: str = "",
    prescription=None,
    operator=None,
):
    """
    ✅ 批次層級的庫存調整：
    - change 正數=加回（例如盤點補回/退藥入庫）
    - change 負數=扣除（例如報廢/盤點扣除）
    """
    new_qty = (batch.quantity or 0) + change
    if new_qty < 0:
        raise ValueError(f"批次 {batch.batch_no} 庫存不足，無法扣除 {abs(change)}  ")

    batch.quantity = new_qty
    batch.save(update_fields=["quantity"])

    StockTransaction.objects.create(
        drug=batch.drug,
        batch=batch,
        change=change,
        reason=reason,
        note=note,
        prescription=prescription,
        operator=operator,
    )

    refresh_stock_quantity(batch.drug)
    return batch


@transaction.atomic
def stock_in(
    drug: Drug,
    quantity: int,
    expiry_date,
    operator=None,
    note: str = "",
    supplier_batch_no: str = "",
):
    """
    ✅ 進貨：建立「新批次」 
    - 不讓人輸入系統批號 batch_no（由 StockBatch.save() 自動生成）
    - supplier_batch_no 若你想留「廠商批號」就放 note 或你之後加欄位
    """
    if quantity <= 0:
        raise ValueError("quantity 必須是正數 ")

    # 每次進貨建立新批次，方便追蹤 
    batch = StockBatch.objects.create(
        drug=drug,
        expiry_date=expiry_date,
        quantity=quantity,
        # batch_no 留空 -> 交給 model.save() 自動產生
        batch_no="",
    )

    StockTransaction.objects.create(
        drug=drug,
        batch=batch,
        change=quantity,
        reason="purchase",
        note=note or (f"進貨入庫{(' / 廠商批號 ' + supplier_batch_no) if supplier_batch_no else ''}"),
        operator=operator,
    )

    refresh_stock_quantity(drug)
    return batch


@transaction.atomic
def destroy_batch(
    batch: StockBatch,
    quantity: int | None = None,
    operator=None,
    note: str = "藥師判斷報廢/銷毀",
):
    """
    ✅ 銷毀/報廢批次庫存（藥師決定）
    - quantity=None => 全部報廢
    - quantity=數字 => 部分報廢
    """
    if quantity is None:
        qty = batch.quantity
    else:
        qty = int(quantity)

    if qty <= 0:
        raise ValueError("報廢數量必須 > 0  ")
    if qty > batch.quantity:
        raise ValueError(f"報廢數量 {qty} 超過批次現有庫存 {batch.quantity}  ")

    batch.quantity -= qty

    # ✅ 若歸零就標記 DESTROYED
    if batch.quantity == 0:
        batch.status = StockBatch.STATUS_DESTROYED
        batch.save(update_fields=["quantity", "status"])  # ✅ 一定要一起存 
    else:
        batch.save(update_fields=["quantity"])

    StockTransaction.objects.create(
        drug=batch.drug,
        batch=batch,
        change=-qty,
        reason="destroy",  # ✅ 這裡改成 destroy  
        note=note,
        operator=operator,
    )

    refresh_stock_quantity(batch.drug)
    return batch


# ---------------------------------------------------------------------
# ✅ 發藥（批次扣庫存）：FEFO + 快過期限制
# ---------------------------------------------------------------------
@transaction.atomic
def use_drug_from_prescription_item(
    item,
    operator=None,
    prescription=None,
    *,
    min_valid_days: int = 0,
):
    """
    從單一處方明細扣庫存 （FEFO + 快過期限制 + 可選療程天數）

    - min_valid_days: 最低還要能放幾天才允許發（例如 7 天）
    - item.treatment_days 若存在且 >0：代表需要效期至少覆蓋療程天數
      會以 max(treatment_days, min_valid_days) 作為最低需求天數 

    若庫存/效期不足：raise ValueError（讓 view 顯示訊息 & 回滾） 
    """
    drug = item.drug
    qty = int(item.quantity or 0)
    if qty <= 0:
        return

    today = timezone.localdate()
    presc = prescription or getattr(item, "prescription", None)

    # 需要覆蓋的天數：療程 vs 最低有效天數，取最大 
    treatment_days = getattr(item, "treatment_days", None)
    need_days = 0
    if treatment_days and int(treatment_days) > 0:
        need_days = int(treatment_days)
    need_days = max(need_days, int(min_valid_days or 0))

    # 最低可接受效期：today + need_days
    # need_days=0 => 只要未過期即可 
    min_expiry_date = today + timedelta(days=need_days)

    remain = qty

    # ✅ 注意：expiry_date__gte 只能出現一次 （你之前 SyntaxError 就是因為重複寫）
    batches = (
    StockBatch.objects
        .select_for_update()
        .filter(
            drug=drug,
            status=StockBatch.STATUS_NORMAL,
            quantity__gt=0,
            expiry_date__gte=min_expiry_date, 
        )
        .order_by("expiry_date", "id")
    )
    if not batches.exists():
        raise ValueError(
            f"藥品「{drug.name}」沒有符合效期要求的可用批次（需效期 >= {min_expiry_date:%Y-%m-%d}） "
        )


    for batch in batches:
        if remain <= 0:
            break

        take = min(batch.quantity, remain)
        if take <= 0:
            continue

        batch.quantity -= take
        batch.save(update_fields=["quantity"])

        StockTransaction.objects.create(
            drug=drug,
            batch=batch,
            change=-take,
            reason="dispense",
            prescription=presc,
            operator=operator,
            note=f"處方明細 #{getattr(item, 'id', '-') } 扣庫存（批號 {batch.batch_no or '-'}）",
        )

        remain -= take

    refresh_stock_quantity(drug)

    if remain > 0:
        raise ValueError(
            f"藥品「{drug.name}」可用庫存/效期不足：仍缺 {remain}{getattr(drug, 'unit', '')}  "
        )

def can_dispense_item(item, *, min_valid_days=0) -> tuple[bool, str, int]:
    drug = item.drug
    qty = int(item.quantity or 0)
    if qty <= 0:
        return True, "", 0

    today = timezone.localdate()
    treatment_days = getattr(item, "treatment_days", None) or 0
    need_days = max(int(treatment_days), int(min_valid_days or 0))
    min_expiry_date = today + timedelta(days=need_days)

    qs = (
        StockBatch.objects
        .filter(
            drug=drug,
            status=StockBatch.STATUS_NORMAL,   # ✅ 關鍵：排除隔離/報廢
            expiry_date__gte=min_expiry_date,  # ✅ 覆蓋療程/最低天數
            quantity__gt=0,
        )
        .order_by("expiry_date", "id")
    )

    remain = qty
    available_total = 0
    for b in qs:
        available_total += b.quantity
        take = min(b.quantity, remain)
        remain -= take
        if remain <= 0:
            return True, "", available_total

    return False, f"{drug.name} 可用庫存/效期不足（需 {qty}，仍缺 {remain}）", available_total


def preview_use_drug_from_prescription_item(
    item,
    *,
    min_valid_days: int = 0,
):
    """
    ✅ 預檢查用（不扣庫存、不寫入）：
    - 檢查是否有「足夠可用庫存」
    - 檢查是否有「效期足以覆蓋療程 / 最低天數」
    - 不鎖、不扣庫存，只做計算 
    - 若不足：raise ValueError
    """
    from datetime import timedelta
    from django.utils import timezone
    from inventory.models import StockBatch

    drug = item.drug
    qty = int(item.quantity or 0)
    if qty <= 0:
        return  # 不需要發藥就直接過 

    today = timezone.localdate()

    treatment_days = getattr(item, "treatment_days", None)
    need_days = 0
    if treatment_days and int(treatment_days) > 0:
        need_days = int(treatment_days)

    need_days = max(need_days, int(min_valid_days or 0))
    min_expiry_date = today + timedelta(days=need_days)

    batches = (
        drug.batches
        .filter(
            status=StockBatch.STATUS_NORMAL,   # ✅ 跟正式扣庫存一致 
            expiry_date__gte=min_expiry_date,
            quantity__gt=0,
        )
        .order_by("expiry_date", "id")
    )

    remain = qty
    for b in batches:
        take = min(b.quantity, remain)
        remain -= take
        if remain <= 0:
            return

    # 走到這裡代表不足 
    raise ValueError(
        f"藥品「{drug.name}」可用庫存/效期不足：仍缺 {remain}{getattr(drug, 'unit', '')}  "
    )

@transaction.atomic
def quarantine_batch(batch: StockBatch,*,operator=None,reason: str = "",note: str = "藥師隔離批次",) -> StockBatch:
    if batch.status == StockBatch.STATUS_QUARANTINE:
        return batch

    batch.status = StockBatch.STATUS_QUARANTINE
    batch.quarantine_reason = (reason or "").strip()
    batch.quarantine_note = (note or "").strip()
    batch.save(update_fields=["status", "quarantine_reason", "quarantine_note"])

    StockTransaction.objects.create(
        drug=batch.drug,
        batch=batch,
        change=0,
        reason="adjust",
        note=f"隔離：{batch.quarantine_reason}；{batch.quarantine_note}".strip("；"),
        operator=operator,
    )
    return batch


@transaction.atomic
def unquarantine_batch(batch: StockBatch,*,operator=None,note: str = "解除隔離批次",) -> StockBatch:
    if batch.status == StockBatch.STATUS_NORMAL:
        return batch

    batch.status = StockBatch.STATUS_NORMAL
    # ✅ 解除隔離就清空原因/備註 
    batch.quarantine_reason = ""
    batch.quarantine_note = ""
    batch.save(update_fields=["status", "quarantine_reason", "quarantine_note"])

    StockTransaction.objects.create(
        drug=batch.drug,
        batch=batch,
        change=0,
        reason="adjust",
        note=note,
        operator=operator,
    )
    return batch

