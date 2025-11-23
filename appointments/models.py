from django.db import models
from django.utils import timezone
from datetime import datetime, time, timedelta, date
from patients.models import Patient
from doctors.models import Doctor, DoctorSchedule
from django.core.exceptions import ValidationError

from datetime import datetime, time, timedelta
from django.db import models  # 你原本就有的應該不用再加，如果沒有就留著喵


class AppointmentManager(models.Manager):
    def get_available_slots(self, doctor, date_):
        """
        傳回某個醫師在某一天可預約的時段列表喵
        doctor : Doctor instance
        date_  : date object 或 'YYYY-MM-DD' 字串都可以
        回傳   : list[datetime.time]
        """
        # 如果是字串就轉成 date 物件喵
        if isinstance(date_, str):
            date_ = datetime.strptime(date_, "%Y-%m-%d").date()

        # 這裡先用簡單版本：09:00–17:00 每 30 分鐘一個時段喵
        start_hour = 9
        end_hour = 17
        step_minutes = 30

        all_slots = []
        current_dt = datetime.combine(date_, time(hour=start_hour, minute=0))
        end_dt = datetime.combine(date_, time(hour=end_hour, minute=0))

        while current_dt <= end_dt:
            all_slots.append(current_dt.time())
            current_dt += timedelta(minutes=step_minutes)

        # 找出這一天這個醫師已經被預約的時間喵
        booked_times = (
            self.filter(doctor=doctor, date=date_)
            .exclude(status="cancelled")  # 如果你的狀態不是這幾個可以自己調喵
            .values_list("time", flat=True)
        )
        booked_set = set(booked_times)

        # 剩下的就是可用時段喵
        available_slots = [t for t in all_slots if t not in booked_set]
        return available_slots

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

    objects = AppointmentManager()

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
