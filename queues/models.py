from django.db import models
from django.utils import timezone
from patients.models import Patient
from doctors.models import Doctor
from appointments.models import Appointment

class VisitTicket(models.Model):
    STATUS_CHOICES = [
        ("WAITING", "候診"),
        ("CALLING", "叫號中"),
        ("IN_ROOM", "看診中"),
        ("DONE", "完成"),
        ("NO_SHOW", "未到"),
    ]
    appointment = models.OneToOneField(
        Appointment, null=True, blank=True, on_delete=models.SET_NULL
    )
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    date = models.DateField()
    number = models.IntegerField("號碼")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="WAITING")
    created_at = models.DateTimeField(default=timezone.now)
    called_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("doctor", "date", "number")]
        ordering = ["date", "doctor", "number"]

    def __str__(self):
        return f"{self.date} {self.doctor} #{self.number} {self.patient}"
