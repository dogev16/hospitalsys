from django.contrib import admin
from .models import Drug, Transaction

@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "unit", "stock", "lot_no", "expiry_date", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "drug", "ttype", "qty", "ref")
    list_filter = ("ttype", "created_at")
    search_fields = ("drug__name", "drug__code", "ref")
