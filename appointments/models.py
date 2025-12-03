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
        根據 DoctorSchedule + 已存在的 Appointment
        計算某位醫師在某一天可預約的時段列表喵
        doctor : Doctor instance
        date_  : date object 或 'YYYY-MM-DD' 字串都可以
        回傳   : list[datetime.time]
        """
        # 字串轉 date 物件
        if isinstance(date_, str):
            date_ = datetime.strptime(date_, "%Y-%m-%d").date()

        weekday = date_.weekday()  # Monday = 0

        # 一次抓出該日所有排班（可能早上 + 下午）喵
        schedules = (
            DoctorSchedule.objects
            .filter(
                doctor=doctor,
                weekday=weekday,
                is_active=True,
            )
            .order_by("start_time")
        )
        if not schedules:
            return []

        # 已經被掛走的時段喵
        taken_times = set(
            self.filter(
                doctor=doctor,
                date=date_,
            ).values_list("time", flat=True)
        )

        now = timezone.localtime()
        tz = timezone.get_current_timezone()

        slots = []

        # 逐一處理每一段排班（早上、下午各跑一次）喵
        for schedule in schedules:
            start_dt = datetime.combine(date_, schedule.start_time)
            end_dt = datetime.combine(date_, schedule.end_time)

            # 避免 naive / aware 混用
            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(start_dt, tz)
            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(end_dt, tz)

            cursor = start_dt
            count_for_this_schedule = 0  # 每一段自己有 max_patients 限制喵

            while cursor <= end_dt:
                t = cursor.time()

                # 如果是今天，就略過太接近現在的時段（例如 30 分鐘內）喵
                if date_ == now.date():
                    if cursor <= now + timedelta(minutes=30):
                        cursor += timedelta(minutes=schedule.slot_minutes)
                        continue

                # 沒被掛走的才算可選喵
                if t not in taken_times:
                    slots.append(t)
                    count_for_this_schedule += 1

                # 這一段排班最多只開到 max_patients 個喵
                if count_for_this_schedule >= schedule.max_patients:
                    break

                cursor += timedelta(minutes=schedule.slot_minutes)

        # 已經依 start_time + 時間順序排好，直接回傳喵
        return slots

class Appointment(models.Model):
    STATUS_BOOKED   = "BOOKED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_DONE     = "DONE"
    STATUS_NO_SHOW  = "NO_SHOW"  # 🆕 預留給「未到 / 過號」

    STATUS_CHOICES = [
        (STATUS_BOOKED, "已掛號"),
        (STATUS_CANCELLED, "已取消"),
        (STATUS_DONE, "已完成"),
        (STATUS_NO_SHOW, "未到 / 過號"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_BOOKED,
    )
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
