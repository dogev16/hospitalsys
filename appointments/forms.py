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
    def __init__(self, *args, **kwargs):
        # 我們等等在 view 會傳進來 patient_initial 
        patient_initial = kwargs.pop("patient_initial", None)
        super().__init__(*args, **kwargs)

        if patient_initial:
            self.fields["patient"].initial = patient_initial
