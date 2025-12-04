from django import forms
from django.forms import inlineformset_factory

from .models import Prescription, PrescriptionItem


class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        # 目前只有醫師備註欄位 ，如果之後有欄位再加進來
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
        fields = ["drug", "quantity", "usage"]
        widgets = {
            "usage": forms.Textarea(attrs={"rows": 2}),
        }


# 🔧 關鍵：這就是 views 要用的 PrescriptionItemFormSet  
PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=1,          # 預設多一列空白
    can_delete=True,  # 可以在畫面上勾選刪除
)
