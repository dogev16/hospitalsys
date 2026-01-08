
from __future__ import annotations

from datetime import timedelta
from django.utils import timezone
from django.db import transaction, models
from django.db.models import Sum

from .models import Drug, StockBatch, StockTransaction



def refresh_stock_quantity(drug: Drug) -> int:
    total = drug.batches.aggregate(total=Sum("quantity"))["total"] or 0
    drug.stock_quantity = total
    drug.save(update_fields=["stock_quantity"])
    return total



@transaction.atomic
def adjust_stock(
    drug: Drug,
    change: int,
    reason: str,
    note: str = "",
    prescription=None,
    operator=None,
):

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

    if quantity <= 0:
        raise ValueError("quantity 必須是正數 ")

    
    batch = StockBatch.objects.create(
        drug=drug,
        expiry_date=expiry_date,
        quantity=quantity,
        
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

    if quantity is None:
        qty = batch.quantity
    else:
        qty = int(quantity)

    if qty <= 0:
        raise ValueError("報廢數量必須 > 0  ")
    if qty > batch.quantity:
        raise ValueError(f"報廢數量 {qty} 超過批次現有庫存 {batch.quantity}  ")

    batch.quantity -= qty

    
    if batch.quantity == 0:
        batch.status = StockBatch.STATUS_DESTROYED
        batch.save(update_fields=["quantity", "status"])  
    else:
        batch.save(update_fields=["quantity"])

    StockTransaction.objects.create(
        drug=batch.drug,
        batch=batch,
        change=-qty,
        reason="destroy", 
        note=note,
        operator=operator,
    )

    refresh_stock_quantity(batch.drug)
    return batch



@transaction.atomic
def use_drug_from_prescription_item(
    item,
    operator=None,
    prescription=None,
    *,
    min_valid_days: int = 0,
):

    drug = item.drug
    qty = int(item.quantity or 0)
    if qty <= 0:
        return

    today = timezone.localdate()
    presc = prescription or getattr(item, "prescription", None)

    
    treatment_days = getattr(item, "treatment_days", None)
    need_days = 0
    if treatment_days and int(treatment_days) > 0:
        need_days = int(treatment_days)
    need_days = max(need_days, int(min_valid_days or 0))

    
    
    min_expiry_date = today + timedelta(days=need_days)

    remain = qty

    
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
            status=StockBatch.STATUS_NORMAL,   
            expiry_date__gte=min_expiry_date,  
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



    drug = item.drug
    qty = int(item.quantity or 0)
    if qty <= 0:
        return  

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
            status=StockBatch.STATUS_NORMAL, 
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

