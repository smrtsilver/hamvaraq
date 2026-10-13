import re

from django import forms
from django.contrib.auth.forms import UserCreationForm

from common.forms import PersianFormMixin
from common.location_forms import LocationMixin

from .models import User

BAD_NAME = re.compile(r"https?://|www\.|@|\d{6,}")


class DisplayNameMixin:
    def clean_display_name(self):
        name = " ".join((self.cleaned_data.get("display_name") or "").split())
        if name and len(name) < 2:
            raise forms.ValidationError("اسم نمایشی حداقل ۲ حرف باشه.")
        if BAD_NAME.search(name):
            raise forms.ValidationError("لینک، شماره یا آیدی تو اسم نمایشی نذار.")
        return name

    def setup_display_name(self, required):
        f = self.fields["display_name"]
        f.required = required
        f.label = "اسم نمایشی"
        f.help_text = "همین اسم کنار کتاب‌ها، نقدها و پیام‌هات نشون داده می‌شه. می‌تونه فارسی باشه."
        f.widget.attrs.update({"autocomplete": "nickname", "maxlength": 40, "placeholder": "مثلاً سارا کتاب‌خوان"})


class SignupForm(DisplayNameMixin, PersianFormMixin, UserCreationForm):
    # تله‌ی ربات: آدم‌ها این فیلد مخفی رو نمی‌بینن و خالی می‌ذارن
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    accept_rules = forms.BooleanField(required=True, error_messages={"required": "برای ثبت‌نام باید قوانین رو بپذیری."})

    class Meta:
        model = User
        fields = ("display_name", "username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_display_name(required=True)
        self.fields["username"].widget.attrs.pop("autofocus", None)
        self.fields["display_name"].widget.attrs["autofocus"] = True
        self.fields["username"].label = "شناسه (برای ورود)"
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


class ProfileForm(DisplayNameMixin, LocationMixin, PersianFormMixin, forms.ModelForm):
    """شهر تو پروفایل اختیاریه؛ برای پیشنهاد نقطه‌ی تحویل و پیش‌فرض ثبت کتاب استفاده می‌شه."""

    location_required = False

    class Meta:
        model = User
        fields = ("display_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_display_name(required=False)
        self.fields["display_name"].help_text += " اگه خالی بمونه، شناسه‌ات نشون داده می‌شه."
        self.setup_location(city=self.instance.city if self.instance.pk else None)
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["email"].help_text = "اختیاریه؛ فقط برای بازیابی رمز."

    def clean(self):
        return self.clean_location(super().clean())

    def save(self, commit=True):
        self.instance.city = self.cleaned_data.get("city")
        return super().save(commit=commit)
