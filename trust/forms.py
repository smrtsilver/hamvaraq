from django import forms

from common.forms import PersianFormMixin

from .models import Report, Vote


class VoteForm(PersianFormMixin, forms.ModelForm):
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


class ReportForm(PersianFormMixin, forms.ModelForm):
    def clean_image(self):
        from django.core.files.uploadedfile import UploadedFile

        from common.images import process_upload

        image = self.cleaned_data.get("image")
        if isinstance(image, UploadedFile):
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError("حجم عکس باید کمتر از ۵ مگابایت باشه.")
            return process_upload(image)
        return image

    class Meta:
        model = Report
        fields = ["reason", "description", "image"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}
