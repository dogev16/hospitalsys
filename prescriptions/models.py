from django.db import models
from django.utils import timezone
from patients.models import Patient
from doctors.models import Doctor
from inventory.models import Drug
from queues.models import VisitTicket

class Prescription(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    date = models.DateField()
    notes = models.TextField(blank=True)
    STATUS_DRAFT = "draft"      # 醫師編輯中
    STATUS_FINAL = "final"      # 醫師確認完成

    status = models.CharField(
        max_length=20,
        default="draft",
        choices=[
            ("draft", "草稿"),
            ("final", "已確認"),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.date} {self.patient} / {self.doctor}"

class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    drug = models.ForeignKey(
        Drug,
        on_delete=models.PROTECT,
        related_name="prescription_items",
    )
    quantity = models.PositiveIntegerField()
    usage = models.TextField(blank=True)

    def __str__(self):
        return f"{self.drug} x {self.quantity}"
