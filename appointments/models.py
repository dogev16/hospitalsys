from datetime import datetime, timedelta, date as date_cls

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from patients.models import Patient
from doctors.models import Doctor, DoctorSchedule, DoctorLeave
from django.db.models import Q


class AppointmentManager(models.Manager):
    def get_available_slots(self, doctor, date_):


        if isinstance(date_, str):
            date_ = datetime.strptime(date_, "%Y-%m-%d").date()

        if DoctorLeave.objects.filter(
            doctor=doctor,
            is_active=True,
            start_date__lte=date_,
            end_date__gte=date_,
        ).exists():
            return []

        weekday = date_.weekday()  # Monday = 0


        schedules = (
            DoctorSchedule.objects
            .filter(doctor=doctor, weekday=weekday, is_active=True)
            .order_by("start_time")
        )
        if not schedules.exists():
            return []

        taken_times = set(
            self.filter(doctor=doctor, date=date_)
                .exclude(status=Appointment.STATUS_CANCELLED)
                .values_list("time", flat=True)
        )


        now = timezone.localtime()
        tz = timezone.get_current_timezone()
        slots = []

        for schedule in schedules:
            start_dt = timezone.make_aware(datetime.combine(date_, schedule.start_time), tz)
            end_dt = timezone.make_aware(datetime.combine(date_, schedule.end_time), tz)

            cursor = start_dt
            count_for_this_schedule = 0

            while cursor < end_dt:
                t = cursor.time()

                if date_ == now.date() and cursor <= now + timedelta(minutes=30):
                    cursor += timedelta(minutes=schedule.slot_minutes)
                    continue

                if t not in taken_times:
                    slots.append(t)
                    count_for_this_schedule += 1

                if count_for_this_schedule >= schedule.max_patients:
                    break

                cursor += timedelta(minutes=schedule.slot_minutes)

        return slots


class Appointment(models.Model):
    STATUS_BOOKED = "BOOKED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_DONE = "DONE"
    STATUS_NO_SHOW = "NO_SHOW"

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

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_BOOKED)
    created_at = models.DateTimeField(default=timezone.now)

    objects = AppointmentManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "date", "time"],
                condition=~Q(status="CANCELLED"),
                name="uniq_active_doctor_date_time",
            )
        ]

    def clean(self):
        leave = DoctorLeave.objects.filter(
            doctor=self.doctor,
            is_active=True,
            start_date__lte=self.date,
            end_date__gte=self.date,
        ).first()
        if leave:
            raise ValidationError(
                f"該醫師於 {leave.start_date} ～ {leave.end_date} 停診"
                + (f"（原因：{leave.reason}）" if leave.reason else "")
            )

        today = timezone.localdate()
        if self.date < today:
            raise ValidationError("不能掛過去的日期")

        if self.date > today + timedelta(days=30):
            raise ValidationError("最多只能預約 30 天內")

        weekday = self.date.weekday()
        schedules = DoctorSchedule.objects.filter(doctor=self.doctor, weekday=weekday, is_active=True)
        if not schedules.exists():
            raise ValidationError("該日期無排班")

        ok = False
        for s in schedules:
            
            if s.start_time <= self.time < s.end_time:
                delta = (
                    datetime.combine(date_cls.min, self.time)
                    - datetime.combine(date_cls.min, s.start_time)
                )
                minutes = delta.total_seconds() / 60
                if minutes % s.slot_minutes == 0:
                    ok = True
                    break

        if not ok:
            raise ValidationError("非合法掛號時段")

    def __str__(self):
        return f"{self.date} {self.time} {self.doctor} {self.patient}"
