from django.db import models
from django.utils import timezone

class Drug(models.Model):
    code = models.CharField("代碼", max_length=50, unique=True)
    name = models.CharField("品名", max_length=200)
    unit = models.CharField("單位", max_length=20, default="TAB")
    stock = models.IntegerField("庫存", default=0)
    lot_no = models.CharField("批號", max_length=50, blank=True)
    expiry_date = models.DateField("效期", null=True, blank=True)
    is_active = models.BooleanField("啟用", default=True)

    def __str__(self):
        return f"{self.code} {self.name}"

class Transaction(models.Model):
    TYPE_CHOICES = [("IN", "入庫"), ("OUT", "出庫")]
    drug = models.ForeignKey(Drug, on_delete=models.CASCADE)
    ttype = models.CharField(max_length=3, choices=TYPE_CHOICES)
    qty = models.IntegerField()
    ref = models.CharField("參考", max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.drug} {self.ttype} {self.qty}"
