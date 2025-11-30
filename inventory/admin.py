from django.contrib import admin
from .models import Drug, StockTransaction


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "form", "strength", "unit",
                    "stock_quantity", "reorder_level", "is_active")
    search_fields = ("code", "name", "generic_name")
    list_filter = ("is_active",)
    ordering = ("code",)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "drug", "ttype", "quantity", "reason")
    list_filter = ("ttype", "created_at")
    search_fields = ("drug__name", "drug__code", "reason")
    ordering = ("-created_at",)
