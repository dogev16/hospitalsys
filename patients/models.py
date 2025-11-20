from django.db import models
from django.db.models import Max
import re

class Patient(models.Model):
    full_name = models.CharField("姓名", max_length=50)
    national_id = models.CharField("身分證", max_length=10, unique=True)
    nhi_no = models.CharField("健保卡號", max_length=20, blank=True)
    birth_date = models.DateField("生日")
    phone = models.CharField("電話", max_length=20, blank=True)
    # ✅ 病歷號：不讓表單編輯，新增時自動產生
    chart_no = models.CharField(
        "病歷號",
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
    )
    address = models.CharField("地址", max_length=200, blank=True)

    def __str__(self):
        return f"{self.chart_no} {self.full_name}"

    def save(self, *args, **kwargs):
        # 只在「沒有病歷號」的情況下自動產生（避免已存在的被改掉）
        if not self.chart_no:
            self.chart_no = self._generate_chart_no()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_chart_no():
        """
        自動產生下一個病歷號：
        找出目前最大的尾碼 → +1 → P001, P002, P003...
        """
        last = Patient.objects.order_by("-id").first()
        if not last or not last.chart_no:
            num = 1
        else:
            m = re.search(r"(\d+)$", last.chart_no)
            if m:
                num = int(m.group(1)) + 1
            else:
                # 如果舊資料沒有數字，保險做法：用 id + 1
                num = last.id + 1
        return f"P{num:03d}"
