from django import forms
from django.forms import inlineformset_factory

from .models import Prescription, PrescriptionItem


class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        
        fields = ["notes"]
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "可輸入醫師備註 …",
                }
            )
        }


class PrescriptionItemForm(forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = ["drug", "quantity", "treatment_days", "usage"]
        widgets = {
            "usage": forms.Textarea(attrs={"rows": 2}),
            "treatment_days": forms.NumberInput(attrs={"min": 1, "class": "form-control"}),
        }



PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=1,          
    can_delete=True, 
)
