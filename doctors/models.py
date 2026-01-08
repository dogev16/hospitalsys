from django.db import models
from django.contrib.auth.models import User

class Doctor(models.Model):
    name = models.CharField("姓名", max_length=50)
    department = models.CharField("科別", max_length=50)
    room = models.CharField("診間", max_length=20, blank=True)
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="使用者帳號"
    )
    department = models.CharField("科別", max_length=50, blank=True) 
    is_active = models.BooleanField("啟用", default=True)

    def __str__(self):
        return f"{self.name} / {self.department}"

    class Meta:
        verbose_name = "醫師"
        verbose_name_plural = "醫師"


class DoctorSchedule(models.Model):
    WEEKDAY_CHOICES = [
        (0, "星期一"),
        (1, "星期二"),
        (2, "星期三"),
        (3, "星期四"),
        (4, "星期五"),
        (5, "星期六"),
        (6, "星期日"),
    ]

    SESSION_CHOICES = [
        ("AM", "上午門診（09:00–12:00）"),
        ("PM", "下午門診（14:00–17:00）"),
    ]

    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="schedules", verbose_name="醫師"
    )
    weekday = models.IntegerField("星期", choices=WEEKDAY_CHOICES)
    session = models.CharField("時段", max_length=2, choices=SESSION_CHOICES)

    # 預設上午 9–12 點、下午 14–17 點，之後微調
    start_time = models.TimeField("開始時間")
    end_time = models.TimeField("結束時間")

    slot_minutes = models.PositiveIntegerField("每位看診間隔（分鐘）", default=10)
    max_patients = models.PositiveIntegerField("每診最多看診人數", default=20)

    is_active = models.BooleanField("啟用", default=True)

    class Meta:
        verbose_name = "醫師門診班表"
        verbose_name_plural = "醫師門診班表"
        unique_together = ("doctor", "weekday", "session")

    def __str__(self):
        return f"{self.doctor} - {self.get_weekday_display()} {self.get_session_display()}"
    
class DoctorLeave(models.Model):
    doctor = models.ForeignKey("doctors.Doctor", on_delete=models.CASCADE, related_name="leaves")
    start_date = models.DateField("請假開始日")
    end_date = models.DateField("請假結束日")
    reason = models.CharField("原因", max_length=200, blank=True)
    is_active = models.BooleanField("啟用", default=True)
    created_at = models.DateTimeField("建立時間", auto_now_add=True)

    class Meta:
        ordering = ("-start_date", "-end_date", "doctor_id")
        indexes = [
            models.Index(fields=["doctor", "start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.doctor} 停診 {self.start_date}~{self.end_date}"

    def clean(self):
        
        from django.core.exceptions import ValidationError
        if self.end_date < self.start_date:
            raise ValidationError("結束日不可早於開始日")