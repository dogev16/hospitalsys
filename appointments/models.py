from django.db import models
from django.utils import timezone
from datetime import datetime, time, timedelta, date
from patients.models import Patient
from doctors.models import Doctor, DoctorSchedule
from django.core.exceptions import ValidationError

class Appointment(models.Model):
    STATUS_CHOICES = [
        ("BOOKED", "已掛號"),
        ("CANCELLED", "已取消"),
        ("DONE", "已完成"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="BOOKED")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("doctor", "date", "time")]

    def clean(self):
        """檢查是否是合理時段。"""
        today = timezone.localdate()
        if self.date < today:
            raise ValidationError("不能掛過去的日期")

        # 只允許 30 天內
        if self.date > today + timedelta(days=30):
            raise ValidationError("最多只能預約 30 天內")

        weekday = self.date.weekday()  # Monday=0
        schedules = DoctorSchedule.objects.filter(doctor=self.doctor, weekday=weekday)
        if not schedules.exists():
            raise ValidationError("該日期無排班")

        ok = False
        for s in schedules:
            # 檢查是否落在排班時間內 & 整除 slot_minutes
            if s.start_time <= self.time < s.end_time:
                delta = (
                    datetime.combine(date.min, self.time)
                    - datetime.combine(date.min, s.start_time)
                )
                minutes = delta.total_seconds() / 60
                if minutes % s.slot_minutes == 0:
                    ok = True
        if not ok:
            raise ValidationError("非合法掛號時段")

    def __str__(self):
        return f"{self.date} {self.time} {self.doctor} {self.patient}"
