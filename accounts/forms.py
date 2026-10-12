from django import forms
from django.contrib.auth.forms import UserCreationForm

from common.forms import PersianFormMixin

from .models import User


class SignupForm(PersianFormMixin, UserCreationForm):
    # تله‌ی ربات: آدم‌ها این فیلد مخفی رو نمی‌بینن و خالی می‌ذارن
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    accept_rules = forms.BooleanField(required=True, error_messages={"required": "برای ثبت‌نام باید قوانین رو بپذیری."})

    class Meta:
        model = User
        fields = ("username", "email", "city")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        # متن‌های پیش‌فرض جنگو ارقام لاتین و لحن رسمی دارن؛ اینا ساده‌ترن
        self.fields["username"].help_text = "حداکثر ۱۵۰ نویسه؛ فقط حرف، عدد و این علامت‌ها: @ . + - _"
        self.fields["password1"].help_text = "حداقل ۸ نویسه؛ نه فقط عدد، نه رمز رایج، و نه شبیه نام کاربری."
        self.fields["password2"].help_text = "همون رمز رو دوباره بنویس."
        self.fields["password1"].label = "رمز"
        self.fields["password2"].label = "تکرار رمز"
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


class ProfileForm(PersianFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("city", "email")
