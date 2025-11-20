from datetime import date as date_cls

from django.shortcuts import render, redirect
from django.contrib import messages

from common.utils import group_required  # 如果你有這個裝飾器
from .models import Appointment
from .forms import AppointmentForm
from .utils import generate_available_slots


@group_required("RECEPTION")  # 或 login_required / 自己的權限裝飾器
def book(request):
    """
    掛號頁面：
    - 初次 GET：顯示空 form，沒有時段
    - 按「載入可約時段」：只產生時段，不直接掛號
    - 按「送出掛號」：真正建立 Appointment
    """
    slots = []

    if request.method == "POST":
        form = AppointmentForm(request.POST)

        # 按的是「載入可約時段」
        if "load_slots" in request.POST:
            if form.is_valid():
                doctor = form.cleaned_data["doctor"]
                appt_date = form.cleaned_data["date"]
                slots = generate_available_slots(doctor, appt_date)
                if not slots:
                    messages.warning(request, "這位醫師該日沒有可掛時段或已滿號")
        else:
            # 按的是「送出掛號」
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
