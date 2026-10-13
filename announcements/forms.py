from django import forms
from django.core.files.uploadedfile import UploadedFile

from common.forms import PersianFormMixin
from common.images import process_upload
from common.location_forms import LocationMixin
from common.widgets import JalaliDateTimeField, JalaliDateTimeWidget

from .models import Announcement


class AnnouncementForm(LocationMixin, PersianFormMixin, forms.ModelForm):
    location_required = False
    starts_at = JalaliDateTimeField(required=False, label="شروع", widget=JalaliDateTimeWidget(years_ahead=2),
                                    help_text="برای خبر لازم نیست؛ برای رویداد تاریخ و ساعت شروع رو انتخاب کن.")
    ends_at = JalaliDateTimeField(required=False, label="پایان", widget=JalaliDateTimeWidget(years_ahead=2), help_text="اختیاری")

    class Meta:
        model = Announcement
        fields = ["title", "kind", "summary", "body", "starts_at", "ends_at", "is_online", "venue", "address", "link",
                  "cover", "organizer", "is_free", "price_note", "club"]
        widgets = {"body": forms.Textarea(attrs={"rows": 8}), "summary": forms.Textarea(attrs={"rows": 3, "maxlength": 300})}
        labels = {"is_online": "این رویداد آنلاینه", "is_free": "ورود رایگانه"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_location(city=self.instance.city if self.instance.pk else None, after="ends_at")
        from clubs.models import Club

        clubs = Club.objects.filter(owner=user, is_active=True) if user is not None else Club.objects.none()
        if clubs.exists():
            self.fields["club"].queryset = clubs
            self.fields["club"].empty_label = "مربوط به باشگاهی نیست"
            self.fields["club"].help_text = "جلسه‌ی باشگاه تو؟ انتخابش کن تا تو صفحه‌ی باشگاه هم دیده بشه."
        else:
            del self.fields["club"]
        self.fields["link"].widget.attrs.update({"dir": "ltr", "placeholder": "نشانی صفحه‌ی ثبت‌نام یا اطلاعات بیشتر", "autocomplete": "off", "inputmode": "url"})
        self.fields["body"].help_text = "قالب‌ها: **پررنگ**، *مورب*، ## تیتر، - فهرست، [متن](لینک)"

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        if isinstance(cover, UploadedFile):
            if cover.size > 5 * 1024 * 1024:
                raise forms.ValidationError("حجم عکس باید کمتر از ۵ مگابایت باشه.")
            return process_upload(cover, max_side=1600)
        return cover

    def clean(self):
        data = self.clean_location(super().clean())
        kind, start, end = data.get("kind"), data.get("starts_at"), data.get("ends_at")
        if kind != Announcement.Kind.NEWS and not start:
            self.add_error("starts_at", "برای رویداد، تاریخ شروع لازمه.")
        if start and end and end < start:
            self.add_error("ends_at", "پایان نمی‌تونه قبل از شروع باشه.")
        if not data.get("is_online") and kind != Announcement.Kind.NEWS and not data.get("city") and not data.get("venue"):
            self.add_error("city", "شهر یا محل برگزاری رو مشخص کن، یا رویداد رو آنلاین بذار.")
        return data

    def save(self, commit=True):
        self.instance.city = self.cleaned_data.get("city")
        return super().save(commit=commit)
