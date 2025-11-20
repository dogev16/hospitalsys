from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Patient
from .forms import PatientForm
from django.db.models import Q 

@login_required
def patient_list(request):
    # 取得搜尋關鍵字，例如 ?q=doge
    query = request.GET.get("q", "").strip()

    # 先抓出所有病人
    patients = Patient.objects.all().order_by("id")

    # 如果有輸入關鍵字，就用姓名 / 身分證 / 電話 / 病歷號來搜尋
    if query:
        patients = patients.filter(
            Q(name__icontains=query) |
            Q(id_number__icontains=query) |
            Q(phone__icontains=query) |
            Q(medical_record_number__icontains=query)
        )

    # 丟到 template
    context = {
        "patients": patients,
        "query": query,
    }
    return render(request, "patients/patient_list.html", context)



@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    return render(request, "patients/patient_detail.html", {"patient": patient})


@login_required
def patient_create(request):
    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("patients:patient_list")
    else:
        form = PatientForm()
    return render(request, "patients/patient_form.html", {"form": form, "mode": "create"})


@login_required
def patient_update(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == "POST":
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            return redirect("patients:patient_detail", pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
    return render(request, "patients/patient_form.html", {"form": form, "mode": "edit", "patient": patient})
