from django.shortcuts import render, redirect, get_object_or_404
from django import forms
from common.utils import group_required
from .models import Drug, Transaction

class DrugForm(forms.ModelForm):
    class Meta:
        model = Drug
        fields = ["code", "name", "unit", "stock", "lot_no", "expiry_date", "is_active"]

@group_required("PHARMACY")
def dashboard(request):
    drugs = Drug.objects.order_by("code")
    return render(request, "inventory/dashboard.html", {"drugs": drugs})

@group_required("PHARMACY")
def new_drug(request):
    if request.method == "POST":
        form = DrugForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("inventory:dashboard")
    else:
        form = DrugForm()
    return render(request, "inventory/drug_form.html", {"form": form})
