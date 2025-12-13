from django import forms
from .models import Drug, StockTransaction, StockBatch


class DrugForm(forms.ModelForm):
    class Meta:
        model = Drug
        fields = ["name", "generic_name", "form", "strength", "unit", "unit_price", "reorder_level", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "generic_name": forms.TextInput(attrs={"class": "form-control"}),
            "form": forms.TextInput(attrs={"class": "form-control"}),
            "strength": forms.TextInput(attrs={"class": "form-control"}),
            "unit": forms.TextInput(attrs={"class": "form-control"}),
            "reorder_level": forms.NumberInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }



        
class StockAdjustForm(forms.Form):
    """
    給庫存調整用的表單 ：
    - reason   : 進貨 / 發藥 / 手動調整
    - quantity : 數量（正整數）
    - note     : 備註
    """
    reason = forms.ChoiceField(
        label="異動類型",
        choices=StockTransaction.REASON_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantity = forms.IntegerField(
        label="異動數量",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    note = forms.CharField(
        label="備註",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

class StockBatchForm(forms.ModelForm):
    class Meta:
        model = StockBatch
        
        fields = ["expiry_date", "quantity"]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "batch_no": "批號",
            "expiry_date": "有效期限",
            "quantity": "進貨數量",
        }