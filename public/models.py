from django.db import models

# Create your models here.
# public/models.py
from django.db import models
from doctors.models import Doctor

class ClinicProfile(models.Model):
    name = models.CharField("醫院名稱", max_length=100, blank=True)
    description = models.TextField("簡介", blank=True)

    phone = models.CharField("聯絡電話", max_length=20)
    address = models.CharField("地址", max_length=255)

    # 門診時間（簡單文字就好）
    opening_hours = models.TextField(
        "門診時間",
        help_text="例如：週一至週五 08:30-12:00 / 13:30-17:00",
    )

    map_url = models.URLField("地圖連結", blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or "Clinic Profile"
    

class Announcement(models.Model):
    LEVEL_INFO = "info"
    LEVEL_NOTICE = "notice"
    LEVEL_BLOCK = "block"

    LEVEL_CHOICES = [
        (LEVEL_INFO, "資訊公告"),
        (LEVEL_NOTICE, "提醒公告"),
        (LEVEL_BLOCK, "管制公告"),
    ]

    title = models.CharField("標題", max_length=200)
    content = models.TextField("內容")

    level = models.CharField(
        "公告類型",
        max_length=10,
        choices=LEVEL_CHOICES,
        default=LEVEL_INFO,
    )

    start_date = models.DateField("開始日期")
    end_date = models.DateField("結束日期")

    is_pinned = models.BooleanField("置頂", default=False)
    show_on_homepage = models.BooleanField("顯示於首頁", default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class PublicRegistrationRequest(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "待審核"),
        (STATUS_APPROVED, "已核准"),
        (STATUS_REJECTED, "已駁回"),
    ]

    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_requests",
        verbose_name="建立的正式掛號",
    )


    # 掛號內容
    department = models.CharField("科別", max_length=50)
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, verbose_name="醫師")
    date = models.DateField("日期")
    period = models.CharField("時段", max_length=2, choices=[("AM", "上午"), ("PM", "下午")])
    time = models.TimeField("時間", null=True, blank=True)

    # 病人填寫資料
    name = models.CharField("姓名", max_length=50)
    national_id = models.CharField("身分證字號", max_length=10)
    birth_date = models.DateField("生日")
    phone = models.CharField("電話", max_length=20)

    # 流程狀態
    status = models.CharField("狀態", max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reject_reason = models.CharField("駁回原因", max_length=200, blank=True)

    created_at = models.DateTimeField("申請時間", auto_now_add=True)
    reviewed_at = models.DateTimeField("審核時間", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "date", "doctor"]),
        ]

    def __str__(self):
        return f"{self.name} {self.date} {self.get_period_display()}（{self.get_status_display()}）"