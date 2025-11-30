from django import forms
from .models import Drug, StockTransaction


class DrugForm(forms.ModelForm):
    class Meta:
        model = Drug
        fields = [
            "code", "name", "generic_name",
            "form", "strength", "unit",
            "stock_quantity", "reorder_level", "is_active"
        ]


class StockInForm(forms.ModelForm):
    """ 入庫（採購） """
    class Meta:
        model = StockTransaction
        fields = ["drug", "quantity", "reason"]


class StockOutForm(forms.ModelForm):
    """ 出庫（調劑） """
    class Meta:
        model = StockTransaction
        fields = ["drug", "quantity", "reason"]
