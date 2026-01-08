from django import forms
from .models import Appointment


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["patient", "doctor", "date", "time"]

        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }
    def __init__(self, *args, **kwargs):
        patient_initial = kwargs.pop("patient_initial", None)
        super().__init__(*args, **kwargs)

        if patient_initial:
            self.fields["patient"].initial = patient_initial
        self.fields["patient"].widget = forms.HiddenInput()
