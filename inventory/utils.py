from django.db import transaction
from .models import Drug, Transaction

@transaction.atomic
def use_drug(code: str, qty: int, ref: str = ""):
    d = Drug.objects.select_for_update().get(code=code)
    if qty > d.stock:
        raise ValueError("庫存不足")
    d.stock -= qty
    d.save()
    Transaction.objects.create(drug=d, ttype="OUT", qty=qty, ref=ref or "rx")
    return d.stock
