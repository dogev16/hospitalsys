from django import forms
from .models import Patient

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "full_name",
            "national_id",
            "nhi_no",
            "birth_date",
            "phone",
            "address",
        ]
