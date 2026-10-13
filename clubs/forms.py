from django import forms

from common.forms import PersianFormMixin
from common.location_forms import LocationMixin

from .models import Club, ClubPost


class ClubForm(LocationMixin, PersianFormMixin, forms.ModelForm):
    location_required = False

    class Meta:
        model = Club
        fields = ["name", "description", "current_title", "current_author", "is_online"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4, "placeholder": "چی می‌خونید، هر چند وقت دور هم جمع می‌شید، کجا…"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_location(city=self.instance.city if self.instance.pk else None, after="is_online")

    def clean(self):
        cleaned = self.clean_location(super().clean())
        self.instance.city = cleaned.get("city")
        return cleaned


class ClubPostForm(forms.ModelForm):
    class Meta:
        model = ClubPost
        fields = ["text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3, "placeholder": "نظرت درباره‌ی فصل‌های این هفته…", "maxlength": 1500})}
        labels = {"text": "پیام تو"}
