from django.db import models
from django.db.models import Max
import re
from django.utils import timezone

class Patient(models.Model):
    # 性別選項
    GENDER_MALE = "M"
    GENDER_FEMALE = "F"
    GENDER_OTHER = "O"
    GENDER_CHOICES = [
        (GENDER_MALE, "男"),
        (GENDER_FEMALE, "女"),
        (GENDER_OTHER, "其他 / 不透露"),
    ]

    BLOOD_A = "A"
    BLOOD_B = "B"
    BLOOD_AB = "AB"
    BLOOD_O = "O"
    BLOOD_UNKNOWN = "UNK"
    BLOOD_TYPE_CHOICES = [
        (BLOOD_A, "A 型"),
        (BLOOD_B, "B 型"),
        (BLOOD_AB, "AB 型"),
        (BLOOD_O, "O 型"),
        (BLOOD_UNKNOWN, "未知"),
    ]

    # ─── 基本資料 ───
    full_name = models.CharField("姓名", max_length=50)
    national_id = models.CharField("身分證", max_length=10, unique=True)
    nhi_no = models.CharField("健保卡號", max_length=20, blank=True)
    gender = models.CharField(
        "性別",
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True,
    )
    birth_date = models.DateField("生日")
    blood_type = models.CharField(
        "血型",
        max_length=3,
        choices=BLOOD_TYPE_CHOICES,
        default=BLOOD_UNKNOWN,
        blank=True,
    )

    # ─── 聯絡資料 ───
    phone = models.CharField("電話", max_length=20, blank=True)
    email = models.EmailField("Email", max_length=100, blank=True)
    address = models.CharField("地址", max_length=200, blank=True)

    # ─── 身體狀況 ───
    height_cm = models.PositiveIntegerField("身高（cm）", null=True, blank=True)
    weight_kg = models.DecimalField(
        "體重（kg）",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )
    allergies = models.TextField(
        "過敏史",
        blank=True,
        help_text="例如：藥物過敏、食物過敏等",
    )
    chronic_diseases = models.TextField(
        "慢性疾病 / 重要病史",
        blank=True,
        help_text="例如：高血壓、糖尿病、心臟病等",
    )
    family_disease_notes = models.TextField(
    "家族病史",
    blank=True,
    null=True,
    help_text="例如：父母高血壓、糖尿病、遺傳疾病等",
    )
    other_risk_notes = models.TextField(
    "其他風險備註",
    blank=True,
    null=True,
    )


    # ─── 緊急聯絡資訊 ───
    emergency_contact_name = models.CharField("緊急聯絡人姓名", max_length=50, blank=True)
    emergency_contact_phone = models.CharField("緊急聯絡人電話", max_length=20, blank=True)
    emergency_contact_relation = models.CharField(
        "與病人關係",
        max_length=50,
        blank=True,
        help_text="例如：父、母、配偶、子女、朋友",
    )

    # ─── 系統欄位 ───
    # ✅ 病歷號：不讓表單編輯，新增時自動產生
    chart_no = models.CharField(
        "病歷號",
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
    )
    note = models.TextField("其他備註", blank=True)

    created_at = models.DateTimeField("建立時間", auto_now_add=True)
    updated_at = models.DateTimeField("最後更新時間", auto_now=True)

    class Meta:
        verbose_name = "病人"
        verbose_name_plural = "病人"
        ordering = ["chart_no"]

    def __str__(self):
        return f"{self.chart_no} {self.full_name}"

    # 統一計算年齡
    @property
    def age(self):
        if not self.birth_date:
            return None
        today = timezone.localdate()
        years = today.year - self.birth_date.year
        # 還沒過生日就 -1
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    def save(self, *args, **kwargs):
        # 只在「沒有病歷號」的情況下自動產生（避免已存在的被改掉喵）
        if not self.chart_no:
            self.chart_no = self._generate_chart_no()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_chart_no():
        """
        自動產生下一個病歷號：
        找出目前最大尾碼 → +1 → P001, P002, P003... 喵
        """
        last = Patient.objects.order_by("-id").first()
        if not last or not last.chart_no:
            num = 1
        else:
            m = re.search(r"(\d+)$", last.chart_no or "")
            if m:
                num = int(m.group(1)) + 1
            else:
                # 如果舊資料沒有數字，就保險用 id + 1 喵
                num = (last.id or 0) + 1
        return f"P{num:03d}"