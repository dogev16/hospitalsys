from django.db import models
from django.utils import timezone
from patients.models import Patient
from doctors.models import Doctor
from appointments.models import Appointment

class VisitTicket(models.Model):
    STATUS_WAITING   = "WAITING"   # 候診
    STATUS_CALLING   = "CALLING"   # 叫號中
    STATUS_IN_ROOM   = "IN_ROOM"   # 看診中
    STATUS_DONE      = "DONE"      # 完成
    STATUS_NO_SHOW   = "NO_SHOW"   # 過號 / 未到

    STATUS_CHOICES = [
        (STATUS_WAITING, "候診"),
        (STATUS_CALLING, "叫號中"),
        (STATUS_IN_ROOM, "看診中"),
        (STATUS_DONE, "完成"),
        (STATUS_NO_SHOW, "未到"),
    ]

    appointment = models.OneToOneField(
        Appointment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)

    date = models.DateField()
    number = models.IntegerField("號碼")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_WAITING,
    )

    created_at = models.DateTimeField(default=timezone.now)
    called_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    is_skipped = models.BooleanField(default=False)      
    call_count = models.PositiveIntegerField(default=0)  

    class Meta:
        unique_together = [("doctor", "date", "number")]
        ordering = ["date", "doctor", "number"]

    def __str__(self):
        return f"{self.date} {self.doctor} #{self.number} {self.patient}"

    def mark_called(self):

        self.status = self.STATUS_CALLING
        self.call_count += 1
        if not self.called_at:
            self.called_at = timezone.now()
        self.save(update_fields=["status", "call_count", "called_at"])

    def mark_finished(self):

        self.status = self.STATUS_DONE
        if not self.finished_at:
            self.finished_at = timezone.now()
        self.save(update_fields=["status", "finished_at"])

    def mark_no_show(self):

        self.status = self.STATUS_NO_SHOW
        self.is_skipped = True
        if not self.finished_at:
            self.finished_at = timezone.now()
        self.save(update_fields=["status", "is_skipped", "finished_at"])