# C:\project\hospitalsys\patients\admin.py
from django.contrib import admin
from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    # list view 顯示欄位
    list_display = (
        "chart_no",
        "full_name",
        "gender_display",
        "birth_date",
        "age_display",
        "phone",
        "national_id",
    )
    search_fields = ("chart_no", "full_name", "national_id", "phone")
    list_filter = ("gender", "blood_type", "birth_date", "created_at")

    readonly_fields = (
        "chart_no",
        "age_display",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("基本資料", {
            "fields": (
                "chart_no",
                "full_name",
                "gender",
                "birth_date",
                "age_display",
                "national_id",
                "nhi_no",
            )
        }),
        ("聯絡資料", {
            "fields": (
                "phone",
                "email",
                "address",
            )
        }),
        ("身體狀況", {
            "fields": (
                "blood_type",
                "height_cm",
                "weight_kg",
                "allergies",
                "chronic_diseases",
                "family_disease_notes", 
                "other_risk_notes",
            )
        }),
        ("緊急聯絡資訊", {
            "fields": (
                "emergency_contact_name",
                "emergency_contact_phone",
                "emergency_contact_relation",
            )
        }),
        ("其他", {
            "fields": (
                "note",
                "created_at",
                "updated_at",
            )
        }),
    )

    # ── admin 顯示用小工具 ──

    def gender_display(self, obj):
        return obj.get_gender_display() or "-"
    gender_display.short_description = "性別"

    def age_display(self, obj):
        return obj.age if obj.age is not None else "-"
    age_display.short_description = "年齡（歲）"
