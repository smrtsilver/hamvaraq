from django import forms

from .models import Report, Vote


class VoteForm(forms.ModelForm):
    like = forms.TypedChoiceField(
        choices=[("1", "👍 لایک"), ("0", "👎 دیسلایک")], coerce=lambda v: v == "1",
        widget=forms.RadioSelect, label="رأی",
    )

    class Meta:
        model = Vote
        fields = ["like", "reason", "comment"]
        widgets = {"comment": forms.TextInput()}

    def clean(self):
        data = super().clean()
        if data.get("like") is True:
            # لایک دلیل نمی‌خواد
            data["reason"] = ""
            data["comment"] = ""
        elif data.get("reason") == Vote.Reason.OTHER and not data.get("comment"):
            self.add_error("comment", "برای «دلیل دیگر» یه توضیح کوتاه بنویس.")
        return data


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "description", "image"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}
