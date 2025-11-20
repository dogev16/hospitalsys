from django.db import models
from django.utils import timezone
from patients.models import Patient
from doctors.models import Doctor
from inventory.models import Drug

class Prescription(models.Model):
    STATUS_CHOICES = [
        ("NEW", "開立"),
        ("READY", "待發藥"),
        ("DISPENSED", "已領藥"),
    ]
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="NEW")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.date} {self.patient} {self.doctor}"

class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    drug = models.ForeignKey(Drug, on_delete=models.PROTECT)
    dose = models.CharField("用法", max_length=100)
    days = models.IntegerField("天數")
    qty = models.IntegerField("數量")

    def __str__(self):
        return f"{self.drug} x{self.qty}"
