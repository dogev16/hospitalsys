from django import forms
from .models import Patient


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient

        # 這裡照臨床邏輯排順序喵（基本 → 聯絡 → 身體狀況 → 風險 → 緊急聯絡 → 備註）
        fields = [
            # ─── 基本資料 ───
            "full_name",
            "national_id",
            "nhi_no",
            "gender",
            "birth_date",
            "blood_type",

            # ─── 聯絡資料 ───
            "phone",
            "email",
            "address",

            # ─── 身體狀況 ───
            "height_cm",
            "weight_kg",
            "allergies",
            "chronic_diseases",

            # ─── 風險 / 家族病史 ───
            "family_disease_notes",
            "other_risk_notes",

            # ─── 緊急聯絡人 ───
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relation",

            # ─── 其他 ───
            "note",
        ]

        # 一些欄位用比較適合的輸入元件喵
        widgets = {
            "birth_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "allergies": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                    "placeholder": "例如：藥物過敏、食物過敏等",
                }
            ),
            "chronic_diseases": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                    "placeholder": "例如：高血壓、糖尿病、心臟病等",
                }
            ),
            "family_disease_notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                    "placeholder": "例如：父母高血壓、糖尿病、遺傳疾病等",
                }
            ),
            "other_risk_notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-control",
                    "placeholder": "其他需要提醒醫師 / 護理師的風險說明",
                }
            ),
            "note": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-control",
                    "placeholder": "其他備註（例如生活習慣、用藥習慣等）",
                }
            ),
        }

        # 如果你不想顯示太多 help_text，也可以在這裡覆蓋掉喵
        help_texts = {
            "height_cm": "可略過，若已知請填整數（公分）",
            "weight_kg": "可略過，若已知請填公斤，最多一位小數",
        }
