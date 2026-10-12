from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignupForm(UserCreationForm):
    # تله‌ی ربات: آدم‌ها این فیلد مخفی رو نمی‌بینن و خالی می‌ذارن
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = User
        fields = ("username", "email", "city")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["email"].help_text = "اختیاریه؛ فقط برای بازیابی رمز."
        self.fields["website"].label = ""

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("درخواست نامعتبر.")
        return ""


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("city", "email")
