from django.db import models
from django.utils import timezone


class Drug(models.Model):
    """
    基本藥品資料：醫生開立處方 + 藥局扣庫存使用
    """
    code = models.CharField("藥品代碼", max_length=50, unique=True)
    name = models.CharField("藥品名稱", max_length=100)
    generic_name = models.CharField("學名 / 成分", max_length=100, blank=True)
    form = models.CharField("劑型", max_length=50, blank=True)        # 錠劑、膠囊、糖漿...
    strength = models.CharField("規格", max_length=50, blank=True)    # 500mg、5mg/mL...
    unit = models.CharField("單位", max_length=20, default="顆")      # 盒、顆、瓶...

    stock_quantity = models.PositiveIntegerField("目前庫存量", default=0)
    reorder_level = models.PositiveIntegerField("安全存量", default=20)

    is_active = models.BooleanField("是否啟用", default=True)

    created_at = models.DateTimeField("建立時間", auto_now_add=True)
    updated_at = models.DateTimeField("更新時間", auto_now=True)

    class Meta:
        verbose_name = "藥品"
        verbose_name_plural = "藥品"

    def __str__(self):
        return f"{self.code} - {self.name}"


# -----------------------------------------
# 庫存異動紀錄（所有入出庫都會記錄）
# -----------------------------------------
class StockTransaction(models.Model):
    TYPE_CHOICES = [
        ("IN", "入庫 / 採購"),
        ("OUT", "出庫 / 調劑"),
        ("ADJ", "庫存調整")
    ]

    drug = models.ForeignKey(Drug, on_delete=models.CASCADE)
    ttype = models.CharField("異動類型", max_length=10, choices=TYPE_CHOICES)
    quantity = models.IntegerField("異動數量")       # 正數 or 負數
    reason = models.CharField("原因 / 備註", max_length=200, blank=True)

    created_at = models.DateTimeField("建立時間", auto_now_add=True)

    class Meta:
        verbose_name = "庫存紀錄"
        verbose_name_plural = "庫存紀錄"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_ttype_display()} - {self.drug.name} ({self.quantity})"
