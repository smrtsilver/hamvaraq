from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "city")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["email"].help_text = "اختیاریه؛ فقط برای بازیابی رمز."


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("city", "email")
