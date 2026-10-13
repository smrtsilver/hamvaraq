from django import forms

from django.core.files.uploadedfile import UploadedFile

from common.forms import PersianFormMixin
from common.images import process_upload
from common.location_forms import LocationMixin

from .isbn import isbn_error
from .isbn import normalize_isbn as isbn_normalize
from .models import Book, BookPhoto, Category, Highlight, Review, ShelfEntry


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


class AuthorDedupMixin:
    """نویسنده‌ی تکراری نساز: نوشتار دیگه‌ی یه نویسنده‌ی موجود ← همون نویسنده؛ نزدیک ولی نه دقیق ← «منظورت این بود؟»."""

    author_suggestions = ()

    def clean_author(self):
        from .authors import canonicalize, match

        raw = " ".join((self.cleaned_data.get("author") or "").split())
        pick = (self.data.get("author_pick") or "").strip()
        if pick:
            return pick[:150]
        kind, value = match(raw)
        if kind == "exact":
            return canonicalize(raw)
        if kind == "fuzzy" and not self.data.get("author_ok"):
            self.author_suggestions = value
            raise forms.ValidationError("این نام خیلی شبیه نویسنده‌ایه که از قبل تو هم‌ورق هست؛ یکی از پیشنهادها رو بزن یا تأیید کن که نویسنده‌ی دیگه‌ایه.")
        return raw


class BookForm(AuthorDedupMixin, LocationMixin, PersianFormMixin, forms.ModelForm):
    extra_photos = MultipleImageField(required=False, label="عکس‌های بیشتر",
                                      help_text=f"تا {BookPhoto.MAX_EXTRA} عکس دیگه (پشت جلد، وضعیت داخل کتاب…)")

    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "category", "condition", "cover", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, default_city=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_location(city=self.instance.city if self.instance.pk else default_city, after="condition")
        self.fields["category"].widget.attrs.update({"data-combobox": "", "data-placeholder": "جستجوی دسته…"})
        _isbn_widget(self.fields["isbn"], self.fields["title"], self.fields["author"])
        # تعداد جای خالی با توجه به عکس‌های فعلی (تو ویرایش)
        self.existing_extra = self.instance.photos.count() if self.instance.pk else 0
        self.fields["cover"].help_text = "عکس اصلی؛ بدون اطلاعات مکانی و فشرده ذخیره می‌شه."

    def clean(self):
        return self.clean_location(super().clean())

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
        self.instance.city = self.cleaned_data["city"]
        book = super().save(commit=commit)
        if commit:
            self.save_extra_photos(book)
        return book

    def save_extra_photos(self, book):
        start = book.photos.count()
        for i, image in enumerate(self.cleaned_data.get("extra_photos") or []):
            BookPhoto.objects.create(book=book, image=image, position=start + i)


class BookFilterForm(LocationMixin, PersianFormMixin, forms.Form):
    location_required = False
    province_only_ok = True
    location_empty = "همه"

    q = forms.CharField(required=False, label="جستجو", widget=forms.TextInput(attrs={
        "placeholder": "عنوان، نویسنده یا شابک", "autocomplete": "off", "enterkeyhint": "search", "type": "search"}))
    category = forms.ModelChoiceField(Category.objects.all(), required=False, empty_label="همه‌ی دسته‌ها", label="دسته",
                                      widget=forms.Select(attrs={"data-combobox": "", "data-placeholder": "همه‌ی دسته‌ها"}))
    condition = forms.ChoiceField(choices=[("", "همه‌ی وضعیت‌ها"), *Book.Condition.choices], required=False, label="وضعیت")
    SORTS = [("new", "جدیدترین"), ("near", "نزدیک‌ترین به من"), ("wanted", "پرتقاضاترین")]
    sort = forms.ChoiceField(choices=SORTS, required=False, label="مرتب‌سازی")
    all = forms.BooleanField(required=False, label="رزروشده‌ها هم نشون بده")     # پیش‌فرض: فقط موجودها

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_location(after="q", province_ph="همه‌ی استان‌ها", city_ph="همه‌ی شهرها")

    def clean(self):
        cleaned = super().clean()
        city, province = cleaned.get("city"), cleaned.get("province")
        if city and province and city.province_id != province.pk:
            cleaned["city"] = None  # لینک قدیمی/دستکاری‌شده: شهر نامربوط رو نادیده بگیر
            self.errors.pop("city", None)
        elif city and not province:
            cleaned["province"] = city.province
        return cleaned


def _isbn_widget(isbn, title, author):
    """فیلد شابک رو به جاوااسکریپت پر‌کردن خودکار وصل می‌کنه."""
    from django.urls import reverse

    isbn.widget.attrs["data-isbn-url"] = reverse("books:isbn")
    isbn.widget.attrs["placeholder"] = "اختیاری؛ عنوان و نویسنده خودکار پر می‌شه"
    title.widget.attrs.update({"data-isbn-title": "", "data-suggest": "title", "autocomplete": "off"})
    author.widget.attrs.update({"data-isbn-author": "", "data-suggest": "author", "autocomplete": "off"})
    title.widget.attrs["data-suggest-url"] = author.widget.attrs["data-suggest-url"] = reverse("books:suggest")


def _clean_isbn(value):
    """شابک معتبر (با رقم کنترل) ← ISBN-13 یکدست؛ ISBN-10 هم به ۱۳رقمی تبدیل می‌شه."""
    value = (value or "").strip()
    if not value:
        return ""
    error = isbn_error(value)
    if error:
        raise forms.ValidationError(error)
    return isbn_normalize(value)


class BulkCommonForm(LocationMixin, PersianFormMixin, forms.Form):
    """مقدارهای مشترک بین همه‌ی کتاب‌های یه ثبت دسته‌ای."""

    def __init__(self, *args, default_city=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_location(city=default_city)

    def clean(self):
        return self.clean_location(super().clean())

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


class RelistForm(LocationMixin, PersianFormMixin, forms.Form):
    """ثبت مجدد کتاب گرفته‌شده: فقط شهر فعلی کتاب رو می‌پرسه."""

    def __init__(self, *args, default_city=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_location(city=default_city)

    def clean(self):
        return self.clean_location(super().clean())


class ShelfAddForm(AuthorDedupMixin, PersianFormMixin, forms.ModelForm):
    """افزودن سریع به قفسه: شابک (اختیاری؛ عنوان و نویسنده خودکار پر می‌شه)، عنوان، نویسنده، وضعیت خواندن."""

    class Meta:
        model = ShelfEntry
        fields = ["isbn", "title", "author", "reading_status"]
        widgets = {"reading_status": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _isbn_widget(self.fields["isbn"], self.fields["title"], self.fields["author"])
        self.fields["isbn"].required = False

    def clean_isbn(self):
        return _clean_isbn(self.cleaned_data.get("isbn"))


class ShelfEntryForm(ShelfAddForm):
    class Meta(ShelfAddForm.Meta):
        fields = ["reading_status", "rating", "review", "note", "cover", "title", "author", "isbn"]
        widgets = {"reading_status": forms.RadioSelect, "rating": forms.RadioSelect,
                   "review": forms.Textarea(attrs={"rows": 5, "placeholder": "نظرت درباره‌ی این کتاب؛ روی قفسه‌ات به بقیه نشون داده می‌شه."}),
                   "note": forms.Textarea(attrs={"rows": 4, "placeholder": "فقط خودت می‌بینی: صفحه‌ای که رسیدی، جمله‌هایی که خوشت اومد…"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].required = False
        self.fields["rating"].choices = [("", "بدون امتیاز")] + [(i, "★" * i) for i in range(1, 6)]
        self.fields["cover"].help_text = "اختیاری؛ عکس جلد خودت. بدون اطلاعات مکانی و فشرده ذخیره می‌شه."
        self.fields["cover"].widget.attrs["accept"] = "image/*"

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        if isinstance(cover, UploadedFile):
            _check_size(cover)
            return process_upload(cover)
        return cover


class HighlightForm(PersianFormMixin, forms.ModelForm):
    class Meta:
        model = Highlight
        fields = ["text", "entry", "title", "author", "page", "is_public"]
        widgets = {"text": forms.Textarea(attrs={"rows": 4, "maxlength": 600, "placeholder": "جمله‌ای که دلت رو برد…"})}
        labels = {"entry": "از کدوم کتاب قفسه‌ات؟", "title": "یا عنوان کتاب", "author": "نویسنده"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entry"].queryset = user.shelf.order_by("title") if user else ShelfEntry.objects.none()
        self.fields["entry"].required = False
        self.fields["entry"].empty_label = "کتاب تو قفسه‌ام نیست"
        self.fields["entry"].widget.attrs.update({"data-combobox": "", "data-placeholder": "جستجوی کتاب قفسه…"})
        self.fields["title"].required = False

    def clean(self):
        data = super().clean()
        if not data.get("entry") and not (data.get("title") or "").strip():
            self.add_error("title", "نقل‌قول باید به یه کتاب ارجاع داشته باشه؛ از قفسه انتخاب کن یا عنوان رو بنویس.")
        return data
