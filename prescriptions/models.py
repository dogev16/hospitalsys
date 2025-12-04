from django.db import models
from django.utils import timezone
from patients.models import Patient
from doctors.models import Doctor
from inventory.models import Drug
from queues.models import VisitTicket
from django.conf import settings

class Prescription(models.Model):
    # －－－ 原本就有的醫師端狀態  －－－
    STATUS_DRAFT = "draft"
    STATUS_FINAL = "final"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "草稿"),
        (STATUS_FINAL, "已完成"),
    ]

    # －－－ 新增：藥局端狀態  －－－
    PHARMACY_PENDING = "pending"   # 醫師已送出，等待領藥
    PHARMACY_DONE    = "done"      # 已領藥
    PHARMACY_CANCELLED = "cancelled" 
    
    PHARMACY_STATUS_CHOICES = [
        (PHARMACY_PENDING, "待領藥"),
        (PHARMACY_DONE,    "已領藥"),
    ]

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT)
    doctor  = models.ForeignKey("doctors.Doctor", on_delete=models.PROTECT)
    date    = models.DateField(default=timezone.now)

    visit_ticket = models.OneToOneField(
        "queues.VisitTicket",
        on_delete=models.PROTECT,
        related_name="prescription",
        null=True,
        blank=True,
    )

    notes   = models.TextField(blank=True)
    status  = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )

    # －－－ 新增給藥局用的欄位  －－－
    pharmacy_status = models.CharField(
        max_length=20,
        choices=PHARMACY_STATUS_CHOICES,
        default=PHARMACY_PENDING,
    )
    dispensed_at = models.DateTimeField(null=True, blank=True)

    dispensed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dispensed_prescriptions",
        verbose_name="領藥藥師",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Prescription #{self.pk} for {self.patient}"


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
