# C:\project\hospitalsys\inventory\models.py
from django.db import models
from django.conf import settings
from django.utils import timezone      
from django.db.models import Max       
import re 

class Drug(models.Model):
    """
    基本藥品資料 ：給醫師開立處方 & 藥局扣庫存用
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
        default=0,
    )

    class Meta:
        verbose_name = "藥品"
        verbose_name_plural = "藥品"

    def save(self, *args, **kwargs):
        """
        如果沒有 code，才自動生成像 DRG0001 這種藥品代碼喵
        """
        if not self.code:
            last = Drug.objects.order_by("id").last()
            new_id = 1 if not last else last.id + 1
            self.code = f"DRG{new_id:04d}"
        super().save(*args, **kwargs)

    @property
    def non_expired_quantity(self):
        """
        回傳「未過期批次」的庫存總和喵
        """
        from django.utils import timezone
        today = timezone.localdate()
        return self.batches.filter(expiry_date__gte=today).aggregate(
            total=models.Sum("quantity")
        )["total"] or 0

    def __str__(self):
        return f"{self.code} - {self.name}"


class StockBatch(models.Model):
    drug = models.ForeignKey(
        "inventory.Drug",
        on_delete=models.CASCADE,
        related_name="batches",
        verbose_name="藥品",
    )
    batch_no = models.CharField("批號", max_length=50, blank=True)
    expiry_date = models.DateField("有效期限")
    quantity = models.PositiveIntegerField("目前庫存量")

    created_at = models.DateTimeField("建立時間", auto_now_add=True)
    updated_at = models.DateTimeField("最後更新時間", auto_now=True)

    class Meta:
        verbose_name = "藥品批次"
        verbose_name_plural = "藥品批次"
        ordering = ["expiry_date", "id"]

    def __str__(self):
        return f"{self.drug.name} / 批號 {self.batch_no or '-'} / 效期 {self.expiry_date} / 庫存 {self.quantity}"

    # 🆕 自動產生批號（只有在 batch_no 為空時才會幫你生喵）
    def save(self, *args, **kwargs):
        if not self.batch_no:
            # 例如：20251211-001 這種格式喵
            today = timezone.localdate()
            date_prefix = today.strftime("%Y%m%d")

            # 找出同一天、同一個藥，批號前綴一樣的最大值
            last_batch_no = (
                StockBatch.objects
                .filter(drug=self.drug, batch_no__startswith=date_prefix)
                .aggregate(max_no=Max("batch_no"))
                .get("max_no")
            )

            if last_batch_no:
                # 從最後面的流水號抓出來 +1
                m = re.search(r"(\d+)$", last_batch_no)
                next_seq = int(m.group(1)) + 1 if m else 1
            else:
                next_seq = 1

            self.batch_no = f"{date_prefix}-{next_seq:03d}"

        super().save(*args, **kwargs)



class StockTransaction(models.Model):
    """
    庫存異動紀錄 ：進貨 / 發藥 / 手動調整
    """
    REASON_CHOICES = [
        ("purchase", "進貨"),
        ("dispense", "發藥"),
        ("return", "退藥"),
        ("adjust", "手動調整"),
    ]

    drug = models.ForeignKey(
        Drug,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="藥品",
    )

    # 🆕 對應到哪一個批次（可空白：舊資料或沒有用批次的紀錄）喵
    batch = models.ForeignKey(
        "inventory.StockBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="批次",
    )

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
