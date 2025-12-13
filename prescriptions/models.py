from django.db import models
from django.utils import timezone
from patients.models import Patient
from doctors.models import Doctor
from inventory.models import Drug
from queues.models import VisitTicket
from django.conf import settings

class Prescription(models.Model):
    # －－－ 醫師端狀態 －－－
    STATUS_DRAFT = "draft"
    STATUS_FINAL = "final"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "草稿"),
        (STATUS_FINAL, "已完成"),
    ]

    # －－－ 藥局端狀態 －－－
    PHARMACY_PENDING   = "pending"    # 醫師已送出，等待領藥
    PHARMACY_DONE      = "done"       # 已領藥
    PHARMACY_CANCELLED = "cancelled"  # 退藥 / 作廢

    PHARMACY_STATUS_CHOICES = [
        (PHARMACY_PENDING,   "待領藥"),
        (PHARMACY_DONE,      "已領藥"),
        (PHARMACY_CANCELLED, "已作廢"),
    ]

    # －－－ 藥師審核狀態 －－－
    VERIFY_PENDING  = "pending"
    VERIFY_APPROVED = "approved"
    VERIFY_REJECTED = "rejected"
    VERIFY_QUERY    = "query"

    VERIFY_STATUS_CHOICES = [
        (VERIFY_PENDING,  "待審核"),
        (VERIFY_APPROVED, "已通過"),
        (VERIFY_REJECTED, "已退回"),
        (VERIFY_QUERY,    "需澄清"),
    ]

    # －－－ 基本欄位 －－－
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

    notes  = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )

    # －－－ 藥局領藥相關欄位 －－－
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

    # －－－ 藥師審核相關欄位 －－－
    verify_status = models.CharField(
        "審核狀態",
        max_length=20,
        choices=VERIFY_STATUS_CHOICES,
        default=VERIFY_PENDING,
    )
    verify_note = models.TextField("審核意見", blank=True)

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_prescriptions",
        verbose_name="審核藥師",
    )
    verified_at = models.DateTimeField("審核時間", null=True, blank=True)

    # －－－ 系統用欄位 －－－
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
    days_supply = models.PositiveIntegerField("療程天數", default=7)
    treatment_days = models.PositiveIntegerField(
        "預計用藥天數",
        default=1,
        help_text="例如連續吃幾天：1、3、7...  ",
    )
    def __str__(self):
        return f"{self.drug} x {self.quantity}"
    
class PrescriptionLog(models.Model):
    """
    處方異動紀錄:
    - 醫師儲存處方
    - 藥局完成領藥
    - 作廢、退藥等
    """
    ACTION_CREATE   = "create"
    ACTION_UPDATE   = "update"
    ACTION_DISPENSE = "dispense"
    ACTION_CANCEL   = "cancel"
    ACTION_RETURN   = "return"

    ACTION_CHOICES = [
        (ACTION_CREATE,   "建立處方"),
        (ACTION_UPDATE,   "修改處方"),
        (ACTION_DISPENSE, "藥局完成領藥"),
        (ACTION_CANCEL,   "作廢處方"),
        (ACTION_RETURN,   "退藥並作廢"),
    ]

    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name="處方",
    )
    action = models.CharField("動作", max_length=20, choices=ACTION_CHOICES)
    message = models.CharField("說明", max_length=200, blank=True)

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人員",
    )

    created_at = models.DateTimeField("時間", auto_now_add=True)

    class Meta:
        verbose_name = "處方異動紀錄"
        verbose_name_plural = "處方異動紀錄"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.get_action_display()}"

class PrescriptionAuditLog(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "建立處方"),
        ("UPDATE", "修改處方"),
        ("DISPENSE", "完成領藥"),
        ("RETURN", "退藥"),
        ("CANCEL", "作廢"),
    ]

    prescription = models.ForeignKey(
        "Prescription",
        on_delete=models.CASCADE,
        related_name="audit_logs",
        verbose_name="處方"
    )

    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人員",
    )

    detail = models.TextField("詳細紀錄", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "處方異動紀錄"
        verbose_name_plural = "處方異動紀錄"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.prescription.id} - {self.action} at {self.created_at}"