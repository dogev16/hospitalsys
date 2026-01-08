from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Max
import re


class Drug(models.Model):
    code = models.CharField("藥品代碼", max_length=50, unique=True)
    name = models.CharField("藥品名稱", max_length=100)
    generic_name = models.CharField("學名 / 成分", max_length=100, blank=True)
    form = models.CharField("劑型", max_length=50, blank=True)
    strength = models.CharField("規格", max_length=50, blank=True)
    unit = models.CharField("單位", max_length=20, default="顆")

    
    stock_quantity = models.PositiveIntegerField("目前庫存量", default=0)
    reorder_level = models.PositiveIntegerField("安全存量", default=0)

    is_active = models.BooleanField("是否啟用", default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    unit_price = models.DecimalField("單價", max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "藥品"
        verbose_name_plural = "藥品"

    def save(self, *args, **kwargs):
        if not self.code:
            last = Drug.objects.order_by("id").last()
            new_id = 1 if not last else last.id + 1
            self.code = f"DRG{new_id:04d}"
        super().save(*args, **kwargs)

    @property
    def non_expired_quantity(self):
        today = timezone.localdate()
        return (
            self.batches.filter(
                expiry_date__gte=today,
                quantity__gt=0,
                status=StockBatch.STATUS_NORMAL,
            ).aggregate(total=models.Sum("quantity"))["total"]
            or 0
        )

    def __str__(self):
        return f"{self.code} - {self.name}"


class StockBatch(models.Model):
    STATUS_NORMAL = "normal"
    STATUS_QUARANTINE = "quarantine"   # 隔離（不可發藥）
    STATUS_DESTROYED = "destroyed"     # 已銷毀（不可發藥）
    STATUS_CHOICES = [
        (STATUS_NORMAL, "正常可用"),
        (STATUS_QUARANTINE, "隔離/待處理"),
        (STATUS_DESTROYED, "已銷毀"),
    ]

    drug = models.ForeignKey(
        "inventory.Drug",
        on_delete=models.CASCADE,
        related_name="batches",
        verbose_name="藥品",
    )
    batch_no = models.CharField("批號", max_length=50, blank=True)
    expiry_date = models.DateField("有效期限")
    quantity = models.PositiveIntegerField("目前庫存量")

    status = models.CharField(
            "批次狀態",
            max_length=20,
            choices=STATUS_CHOICES,
            default=STATUS_NORMAL,
        )    
    destroyed_at = models.DateTimeField("銷毀時間", null=True, blank=True)
    destroy_reason = models.CharField("銷毀原因", max_length=200, blank=True)

    created_at = models.DateTimeField("建立時間", auto_now_add=True)
    updated_at = models.DateTimeField("最後更新時間", auto_now=True)
    QUARANTINE_REASON_CHOICES = [
        ("packaging", "包裝異常"),
        ("temperature", "溫控異常"),
        ("recall", "疑似召回/批次問題"),
        ("source", "來源/文件不齊"),
        ("other", "其他"),
    ]
    quarantine_reason = models.CharField("隔離原因", max_length=50, blank=True, default="")
    quarantine_note = models.CharField("隔離備註", max_length=255, blank=True, default="")


    class Meta:
        verbose_name = "藥品批次"
        verbose_name_plural = "藥品批次"
        ordering = ["expiry_date", "id"]
        constraints = [
            models.UniqueConstraint(fields=["drug", "batch_no"], name="uniq_drug_batch_no"),
        ]

    def __str__(self):
        return f"{self.drug.name} / 批號 {self.batch_no or '-'} / 效期 {self.expiry_date} / 庫存 {self.quantity}"

    def save(self, *args, **kwargs):
        
        if not self.batch_no:
            today = timezone.localdate()
            date_prefix = today.strftime("%Y%m%d")

            
            last_batch_no = (
                StockBatch.objects
                .filter(drug=self.drug, batch_no__startswith=date_prefix)
                .aggregate(max_no=Max("batch_no"))
                .get("max_no")
            )

            if last_batch_no:
                m = re.search(r"(\d+)$", last_batch_no)
                next_seq = int(m.group(1)) + 1 if m else 1
            else:
                next_seq = 1

            self.batch_no = f"{date_prefix}-{next_seq:03d}"

        super().save(*args, **kwargs)


class StockTransaction(models.Model):
    REASON_CHOICES = [
        ("purchase", "進貨"),
        ("dispense", "發藥"),
        ("return", "退藥"),
        ("adjust", "手動調整"),
        ("destroy", "報廢/銷毀"),
    ]

    drug = models.ForeignKey(Drug, on_delete=models.CASCADE, related_name="transactions", verbose_name="藥品")

    batch = models.ForeignKey(
        "inventory.StockBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="批次",
    )

    change = models.IntegerField("異動數量")
    reason = models.CharField("原因", max_length=20, choices=REASON_CHOICES)
    note = models.CharField("備註", max_length=200, blank=True)

    prescription = models.ForeignKey(
        "prescriptions.Prescription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
        verbose_name="相關處方",
    )

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_operations",
        verbose_name="操作人員",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "庫存異動"
        verbose_name_plural = "庫存異動"

    def __str__(self):
        sign = "+" if self.change >= 0 else ""
        batch_part = f" / 批號 {self.batch.batch_no}" if self.batch else ""
        return f"{self.drug.name}{batch_part} {sign}{self.change} ({self.get_reason_display()})"
