from datetime import date as date_cls

from django.shortcuts import render, redirect
from django.contrib import messages

from common.utils import group_required  
from .models import Appointment
from .forms import AppointmentForm
from .utils import generate_available_slots


@group_required("RECEPTION")  
def book(request):

    slots = []

    if request.method == "POST":
        form = AppointmentForm(request.POST)

        if "load_slots" in request.POST:
            if form.is_valid():
                doctor = form.cleaned_data["doctor"]
                appt_date = form.cleaned_data["date"]
                slots = generate_available_slots(doctor, appt_date)
                if not slots:
                    messages.warning(request, "這位醫師該日沒有可掛時段或已滿號")
        else:
            if form.is_valid():
                appointment = form.save()
                messages.success(request, "掛號成功！")
                return redirect("appointments:book")
    else:
        form = AppointmentForm()

    return render(
        request,
        "appointments/book.html",
        {
            "form": form,
            "slots": slots,
        },
    )
