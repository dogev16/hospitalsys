# C:\project\hospitalsys\inventory\models.py
from django.db import models


class Drug(models.Model):
    """
    基本藥品資料喵：給醫師開立處方 & 藥局扣庫存用
    """
    code = models.CharField("藥品代碼", max_length=50, unique=True)
    name = models.CharField("藥品名稱", max_length=100)
    generic_name = models.CharField("學名 / 成分", max_length=100, blank=True)
    form = models.CharField("劑型", max_length=50, blank=True)        # 錠劑、膠囊、糖漿...
    strength = models.CharField("規格", max_length=50, blank=True)    # 500mg、5mg/mL...
    unit = models.CharField("單位", max_length=20, default="顆")      # 盒、顆、瓶...

    stock_quantity = models.PositiveIntegerField("目前庫存量", default=0)
    reorder_level = models.PositiveIntegerField("安全存量", default=0)

    is_active = models.BooleanField("是否啟用", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    unit_price = models.DecimalField(
        "單價",
        max_digits=10,      # 最多 99999999.99 這種等級
        decimal_places=2,
        default=0
    )

    class Meta:
        verbose_name = "藥品"
        verbose_name_plural = "藥品"

    def save(self, *args, **kwargs):
    # 如果沒有 code，才自動生成
        if not self.code:
            last = Drug.objects.order_by("id").last()
            new_id = 1 if not last else last.id + 1
            self.code = f"DRG{new_id:04d}"  # 生成 DRG0001 格式
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"


class StockTransaction(models.Model):
    """
    庫存異動紀錄喵：進貨 / 發藥 / 手動調整
    """
    REASON_CHOICES = [
        ("purchase", "進貨"),
        ("dispense", "發藥"),
        ("adjust", "手動調整"),
    ]

    drug = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name="transactions")
    change = models.IntegerField("異動數量")  # 正數=增加, 負數=減少
    reason = models.CharField("原因", max_length=20, choices=REASON_CHOICES)
    note = models.CharField("備註", max_length=200, blank=True)

    # 之後可以接 prescriptions.Prescription（現在先預留欄位）
    prescription = models.ForeignKey(
        "prescriptions.Prescription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "庫存異動"
        verbose_name_plural = "庫存異動"

    def __str__(self):
        sign = "+" if self.change >= 0 else ""
        return f"{self.drug.name} {sign}{self.change} ({self.get_reason_display()})"
