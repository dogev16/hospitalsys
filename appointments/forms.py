from django import forms
from .models import Appointment


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["patient", "doctor", "date", "time"]

        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            # time 會被我們在 template 用下拉選單覆蓋，所以這邊樣式不重要
        }
