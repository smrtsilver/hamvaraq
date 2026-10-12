from django import forms

from .models import NotificationPreference


class PreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = ["push_exchange", "push_chat", "push_wishlist", "push_other"]
