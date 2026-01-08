from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Patient
from .forms import PatientForm
from django.db.models import Q 
from appointments.models import Appointment


@login_required
def patient_list(request):
    
    query = request.GET.get("q", "").strip()

    
    patients = Patient.objects.all().order_by("id")

    
    if query:
        patients = patients.filter(
            Q(name__icontains=query) |
            Q(id_number__icontains=query) |
            Q(phone__icontains=query) |
            Q(medical_record_number__icontains=query)
        )

    
    context = {
        "patients": patients,
        "query": query,
    }
    return render(request, "patients/patient_list.html", context)



@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    
    appointments = (
        Appointment.objects
        .filter(patient=patient)
        .select_related("doctor")          
        .order_by("-date", "-time")        
    )

    context = {
        "patient": patient,
        "appointments": appointments,
    }
    return render(request, "patients/patient_detail.html", context)



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
