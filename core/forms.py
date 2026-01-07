# core/forms.py
from __future__ import annotations

import random
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

CAPTCHA_SESSION_KEY = "login_captcha_answer"
CAPTCHA_QUESTION_KEY = "login_captcha_question"


class CaptchaAuthenticationForm(AuthenticationForm):
    """
    簡易人機驗證：顯示算術題（存在 session），使用者輸入正確才允許登入。
    """

    captcha = forms.CharField(
        label="人機驗證",
        required=True,
        max_length=10,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "inputmode": "numeric",
            "placeholder": "請輸入答案",
        })
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)

        # 統一加上基本 attrs（可配合你 app.css 的樣式）
        self.fields["username"].widget.attrs.update({"autocomplete": "username"})
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})

        # 產生題目（只在 session 沒有題目時）
        if request is not None:
            sess = request.session
            if CAPTCHA_SESSION_KEY not in sess or CAPTCHA_QUESTION_KEY not in sess:
                a = random.randint(2, 9)
                b = random.randint(1, 9)
                sess[CAPTCHA_SESSION_KEY] = str(a + b)
                sess[CAPTCHA_QUESTION_KEY] = f"{a} + {b} = ?"
                sess.modified = True

    def clean(self):
        cleaned = super().clean()

        request = getattr(self, "request", None)
        if request is None:
            raise ValidationError("系統無法取得驗證資訊，請重新整理後再試。")

        expected = request.session.get(CAPTCHA_SESSION_KEY)
        got = (self.cleaned_data.get("captcha") or "").strip()

        if not expected or got != str(expected):
            # 答錯就重生新題目（避免一直猜同一題）
            a = random.randint(2, 9)
            b = random.randint(1, 9)
            request.session[CAPTCHA_SESSION_KEY] = str(a + b)
            request.session[CAPTCHA_QUESTION_KEY] = f"{a} + {b} = ?"
            request.session.modified = True
            raise ValidationError("人機驗證答案錯誤，請再試一次。")

        return cleaned
