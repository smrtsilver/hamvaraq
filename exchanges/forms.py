from django import forms

from common.forms import PersianFormMixin
from trust.models import Report


class DisputeForm(PersianFormMixin, forms.Form):
    reason = forms.ChoiceField(
        choices=[(Report.Reason.NO_SHOW, "طرف مقابل نیومد یا جواب نمی‌ده"), (Report.Reason.BAD_BOOK, "کتاب با توضیحات نمی‌خونه"),
                 (Report.Reason.SCAM, "ماجرا مشکوکه (کلاهبرداری یا فروش)"), (Report.Reason.OTHER, "سایر")],
        label="مشکل چیه؟",
    )
    description = forms.CharField(required=False, max_length=500, label="توضیح", widget=forms.Textarea(attrs={"rows": 3}))
