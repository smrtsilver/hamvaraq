from django import forms

from django.core.files.uploadedfile import UploadedFile

from common.forms import PersianFormMixin
from common.images import process_upload
from common.models import City

from .isbn import normalize as isbn_normalize
from .models import Book, BookPhoto, Category, Review


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """چند عکس با یک ورودی؛ هر کدوم جدا اعتبارسنجی می‌شه."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [single(f, initial) for f in files]


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _check_size(f):
    if f and hasattr(f, "size") and f.size > MAX_UPLOAD_BYTES:
        raise forms.ValidationError("حجم هر عکس باید کمتر از ۵ مگابایت باشه.")


class BookForm(PersianFormMixin, forms.ModelForm):
    extra_photos = MultipleImageField(required=False, label="عکس‌های بیشتر",
                                      help_text=f"تا {BookPhoto.MAX_EXTRA} عکس دیگه (پشت جلد، وضعیت داخل کتاب…)")

    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "category", "condition", "city", "cover", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _isbn_widget(self.fields["isbn"], self.fields["title"], self.fields["author"])
        # تعداد جای خالی با توجه به عکس‌های فعلی (تو ویرایش)
        self.existing_extra = self.instance.photos.count() if self.instance.pk else 0
        self.fields["cover"].help_text = "عکس اصلی؛ بدون اطلاعات مکانی و فشرده ذخیره می‌شه."

    def clean_isbn(self):
        return _clean_isbn(self.cleaned_data.get("isbn"))

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        if isinstance(cover, UploadedFile):  # آپلود تازه (نه عکس قبلی و نه «پاک کردن»)
            _check_size(cover)
            return process_upload(cover)
        return cover

    def clean_extra_photos(self):
        photos = self.cleaned_data.get("extra_photos") or []
        room = BookPhoto.MAX_EXTRA - self.existing_extra
        if len(photos) > room:
            raise forms.ValidationError(f"حداکثر {BookPhoto.MAX_EXTRA} عکس اضافه (الان {self.existing_extra} تا داری).")
        for p in photos:
            _check_size(p)
        return [process_upload(p) for p in photos]

    def save(self, commit=True):
        book = super().save(commit=commit)
        if commit:
            self.save_extra_photos(book)
        return book

    def save_extra_photos(self, book):
        start = book.photos.count()
        for i, image in enumerate(self.cleaned_data.get("extra_photos") or []):
            BookPhoto.objects.create(book=book, image=image, position=start + i)


class BookFilterForm(PersianFormMixin, forms.Form):
    q = forms.CharField(required=False, label="جستجو")
    city = forms.ModelChoiceField(City.objects.all(), required=False, empty_label="همه‌ی شهرها", label="شهر")
    category = forms.ModelChoiceField(Category.objects.all(), required=False, empty_label="همه‌ی دسته‌ها", label="دسته")
    condition = forms.ChoiceField(choices=[("", "همه‌ی وضعیت‌ها"), *Book.Condition.choices], required=False, label="وضعیت")


def _isbn_widget(isbn, title, author):
    """فیلد شابک رو به جاوااسکریپت پر‌کردن خودکار وصل می‌کنه."""
    from django.urls import reverse

    isbn.widget.attrs["data-isbn-url"] = reverse("books:isbn")
    isbn.widget.attrs["placeholder"] = "اختیاری؛ عنوان و نویسنده خودکار پر می‌شه"
    title.widget.attrs["data-isbn-title"] = ""
    author.widget.attrs["data-isbn-author"] = ""


def _clean_isbn(value):
    value = (value or "").strip()
    if not value:
        return ""
    normalized = isbn_normalize(value)
    if not normalized:
        raise forms.ValidationError("شابک باید ۱۰ یا ۱۳ رقم باشه.")
    return normalized


class BulkCommonForm(PersianFormMixin, forms.Form):
    """مقدارهای مشترک بین همه‌ی کتاب‌های یه ثبت دسته‌ای."""

    city = forms.ModelChoiceField(City.objects.all(), label="شهر")
    condition = forms.ChoiceField(choices=Book.Condition.choices, initial=Book.Condition.USED, label="وضعیت فیزیکی")


class BulkRowForm(PersianFormMixin, forms.Form):
    isbn = forms.CharField(required=False, max_length=20, label="شابک")
    title = forms.CharField(required=False, max_length=200, label="عنوان")
    author = forms.CharField(required=False, max_length=150, label="نویسنده")
    category = forms.ModelChoiceField(Category.objects.all(), required=False, label="دسته")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _isbn_widget(self.fields["isbn"], self.fields["title"], self.fields["author"])
        self.fields["isbn"].widget.attrs.pop("placeholder")

    def clean_isbn(self):
        return _clean_isbn(self.cleaned_data.get("isbn"))

    def clean(self):
        data = super().clean()
        filled = any(data.get(k) for k in ("isbn", "title", "author"))
        if filled and not (data.get("title") and data.get("author")):
            raise forms.ValidationError("برای هر ردیف، عنوان و نویسنده لازمه.")
        return data


class ReviewForm(PersianFormMixin, forms.ModelForm):
    class Meta:
        model = Review
        fields = ["stars", "text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}
