from datetime import timedelta
from django.utils import timezone

from inventory.models import Drug, StockBatch, StockTransaction
from inventory.utils import refresh_stock_quantity

today = timezone.localdate()
init_expiry = today + timedelta(days=365 * 3)

targets = ["DRG0001", "DRG0003", "DRG0004"]

for code in targets:
    drug = Drug.objects.get(code=code)
    old_qty = int(drug.stock_quantity or 0)

    if old_qty <= 0:
        print(code, drug.name, "skip (0)")
        continue

    if StockBatch.objects.filter(drug=drug, batch_no="INIT").exists():
        print(code, drug.name, "already has INIT batch, skip")
        refresh_stock_quantity(drug)
        continue

    batch = StockBatch.objects.create(
        drug=drug,
        batch_no="INIT",
        expiry_date=init_expiry,
        quantity=old_qty,
        status=StockBatch.STATUS_NORMAL,
    )

    StockTransaction.objects.create(
        drug=drug,
        batch=batch,
        change=old_qty,
        reason="purchase",
        note="初始化舊系統庫存 -> INIT 批次",
    )

    refresh_stock_quantity(drug)
    print(code, drug.name, "OK -> INIT", old_qty)
