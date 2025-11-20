from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from common.utils import group_required
from .models import Prescription
from inventory.utils import use_drug

@group_required("PHARMACY")
def pharmacy_panel(request):
    today = timezone.localdate()
    items = Prescription.objects.filter(date=today, status__in=["READY", "DISPENSED"])
    return render(request, "prescriptions/pharmacy.html", {"items": items})

@group_required("PHARMACY")
def dispense(request, pk):
    rx = get_object_or_404(Prescription, pk=pk)
    if rx.status == "DISPENSED":
        return redirect("prescriptions:pharmacy_panel")
    # 簡單扣庫存
    for item in rx.items.all():
        use_drug(item.drug.code, item.qty, ref=f"RX#{rx.pk}")
    rx.status = "DISPENSED"
    rx.save()
    return redirect("prescriptions:pharmacy_panel")
