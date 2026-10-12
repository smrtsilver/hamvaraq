from django import forms

from .isbn import normalize as isbn_normalize
from .models import Book, Category, Review
from common.models import City


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "category", "condition", "city", "cover", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _isbn_widget(self.fields["isbn"], self.fields["title"], self.fields["author"])

    def clean_isbn(self):
        return _clean_isbn(self.cleaned_data.get("isbn"))

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        if cover and hasattr(cover, "size") and cover.size > 5 * 1024 * 1024:
            raise forms.ValidationError("حجم عکس باید کمتر از ۵ مگابایت باشه.")
        return cover


class BookFilterForm(forms.Form):
    q = forms.CharField(required=False, label="جستجو")
    city = forms.ModelChoiceField(City.objects.all(), required=False, empty_label="همه‌ی شهرها", label="شهر")
    category = forms.ModelChoiceField(Category.objects.all(), required=False, empty_label="همه‌ی دسته‌ها", label="دسته")
    condition = forms.ChoiceField(choices=[("", "همه‌ی وضعیت‌ها"), *Book.Condition.choices], required=False, label="وضعیت")


def _isbn_widget(isbn, title, author):
    """فیلد شابک رو به جاوااسکریپت پر‌کردن خودکار وصل می‌کنه."""
    from django.urls import reverse

    isbn.widget.attrs["data-isbn-url"] = reverse("books:isbn")
    isbn.widget.attrs["placeholder"] = "اختیاری؛ با وارد کردنش عنوان و نویسنده پر می‌شه"
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


class BulkCommonForm(forms.Form):
    """مقدارهای مشترک بین همه‌ی کتاب‌های یه ثبت دسته‌ای."""

    city = forms.ModelChoiceField(City.objects.all(), label="شهر")
    condition = forms.ChoiceField(choices=Book.Condition.choices, initial=Book.Condition.USED, label="وضعیت فیزیکی")


class BulkRowForm(forms.Form):
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


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["stars", "text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}
