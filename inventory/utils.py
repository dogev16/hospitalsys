from django.db import transaction
from .models import Drug, StockTransaction


def adjust_stock(drug: Drug, qty: int, ttype: str, reason: str = ""):
    """
    藥品庫存調整（IN / OUT / ADJ）
    qty：正數=增加庫存、負數=扣庫存
    """
    with transaction.atomic():
        drug.stock_quantity += qty
        if drug.stock_quantity < 0:
            raise ValueError("庫存不足，扣庫存失敗！")
        drug.save()

        StockTransaction.objects.create(
            drug=drug,
            ttype=ttype,
            quantity=qty,
            reason=reason,
        )


def use_drug(drug: Drug, qty: int, ref: str | None = None, note: str = ""):
    """
    給 prescriptions 用的舊 API 包裝：
    - qty：要使用的數量（正數）
    - ref：可以傳處方單號之類的字（選填）
    - note：額外備註（選填）

    內部實際會呼叫 adjust_stock 做 OUT 扣庫存。
    """
    if qty <= 0:
        return

    if note:
        reason = note
    elif ref:
        reason = f"處方調劑（ref={ref}）"
    else:
        reason = "處方調劑"

    adjust_stock(drug, -qty, "OUT", reason)
