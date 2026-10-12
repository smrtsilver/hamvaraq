from django import forms

from common.forms import PersianFormMixin

from .models import Ticket


class TicketForm(PersianFormMixin, forms.ModelForm):
    website = forms.CharField(required=False, label="وب‌سایت", widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))  # تله‌ی ربات

    class Meta:
        model = Ticket
        fields = ["category", "subject", "message", "page_url", "contact"]
        widgets = {
            "subject": forms.TextInput(attrs={"placeholder": "مثلاً: دکمه‌ی درخواست کتاب کار نمی‌کنه", "autocomplete": "off"}),
            "message": forms.Textarea(attrs={"rows": 6, "placeholder": "چی شد؟ چه کاری می‌کردی؟ چه اتفاقی افتاد و انتظار داشتی چی بشه؟"}),
            "page_url": forms.HiddenInput(),
            "contact": forms.TextInput(attrs={"placeholder": "ایمیل یا آیدی تلگرام، اگه می‌خوای باهات تماس بگیریم", "autocomplete": "off", "dir": "ltr"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None and user.is_authenticated:
            del self.fields["contact"]
        self.fields["message"].min_length = 10

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("نامعتبر")
        return ""

    def clean_page_url(self):
        url = (self.cleaned_data.get("page_url") or "")[:300]
        return url if url.startswith("/") else ""

    def clean_message(self):
        text = self.cleaned_data["message"].strip()
        if len(text) < 10:
            raise forms.ValidationError("حداقل چند کلمه توضیح بده تا بتونیم پیگیری کنیم.")
        return text
