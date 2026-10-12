from django import forms

from .models import Book, Category
from common.models import City


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "category", "condition", "city", "cover", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

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
