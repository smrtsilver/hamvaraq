from django import forms

from challenges.models import Challenge
from common.forms import PersianFormMixin
from common.models import SiteSetting
from common.widgets import JalaliDateTimeField, JalaliDateTimeWidget
from support.models import Ticket
from trust.models import Report


class NoteForm(forms.Form):
    note = forms.CharField(label="دلیل", max_length=300, widget=forms.TextInput(attrs={"placeholder": "دلیل (برای کاربر و لاگ ثبت می‌شه)", "autocomplete": "off"}))


class PointsForm(forms.Form):
    delta = forms.IntegerField(label="تغییر امتیاز", min_value=-50, max_value=50, widget=forms.NumberInput(attrs={"placeholder": "مثلاً ۲ یا -۱", "dir": "ltr"}))
    note = forms.CharField(label="دلیل", max_length=300, widget=forms.TextInput(attrs={"placeholder": "دلیل", "autocomplete": "off"}))

    def clean_delta(self):
        d = self.cleaned_data["delta"]
        if d == 0:
            raise forms.ValidationError("صفر که تغییری نیست.")
        return d


class DecisionForm(PersianFormMixin, forms.Form):
    decision = forms.ChoiceField(choices=[c for c in Report.Decision.choices if c[0]], label="تصمیم")
    decision_note = forms.CharField(label="دلیل تصمیم", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "برای گزارش‌دهنده و متخلف ثبت می‌شه"}))


class TicketReplyForm(PersianFormMixin, forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["status", "reply"]
        widgets = {"reply": forms.Textarea(attrs={"rows": 5, "placeholder": "پاسخ برای کاربر (اختیاری)"})}


class ChallengeForm(PersianFormMixin, forms.ModelForm):
    starts_at = JalaliDateTimeField(label="شروع", widget=JalaliDateTimeWidget(years_ahead=2))
    ends_at = JalaliDateTimeField(label="پایان", widget=JalaliDateTimeWidget(years_ahead=2))

    class Meta:
        model = Challenge
        fields = ["title", "description", "kind", "target", "starts_at", "ends_at", "is_active"]

    def clean(self):
        c = super().clean()
        if c.get("starts_at") and c.get("ends_at") and c["ends_at"] <= c["starts_at"]:
            self.add_error("ends_at", "پایان باید بعد از شروع باشه.")
        return c


class SiteSettingForm(PersianFormMixin, forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ["tagline", "hero_title", "hero_subtitle", "cta_title", "cta_text", "footer_text", "telegram_url", "instagram_url",
                  "contact_email", "banner_active", "banner_text", "banner_url"]
        widgets = {"hero_subtitle": forms.Textarea(attrs={"rows": 3}), "cta_text": forms.Textarea(attrs={"rows": 3})}
