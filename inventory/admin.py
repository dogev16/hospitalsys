# C:\project\hospitalsys\inventory\admin.py
from django.contrib import admin
from .models import Drug, StockTransaction
from .models import StockBatch


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "stock_quantity",
        "reorder_level",
        "is_active",
        "updated_at",
    )
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "drug",
        "reason",     # purchase / dispense / adjust
        "change",     # 正負數
        "note",
        "created_at",
    )
    list_filter = ("reason", "created_at")
    search_fields = ("drug__name", "note")

@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = ("drug", "batch_no", "expiry_date", "quantity")
    list_filter = ("expiry_date", "drug")
    search_fields = ("drug__name", "batch_no")
