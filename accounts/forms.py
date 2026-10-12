from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignupForm(UserCreationForm):
    # تله‌ی ربات: آدم‌ها این فیلد مخفی رو نمی‌بینن و خالی می‌ذارن
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    accept_rules = forms.BooleanField(required=True, error_messages={"required": "برای ثبت‌نام باید قوانین رو بپذیری."})

    class Meta:
        model = User
        fields = ("username", "email", "city")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["email"].help_text = "اختیاریه؛ فقط برای بازیابی رمز."
        self.fields["website"].label = ""
        from django.urls import reverse
        from django.utils.html import format_html

        self.fields["accept_rules"].label = format_html(
            '<a href="{}" target="_blank" rel="noopener">قوانین هم‌ورق</a> رو خوندم و می‌پذیرم', reverse("rules"))

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("درخواست نامعتبر.")
        return ""


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("city", "email")
