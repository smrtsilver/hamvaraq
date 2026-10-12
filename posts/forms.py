from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q

from books.models import Book, Category
from common.forms import PersianFormMixin
from common.images import process_upload
from common.richtext import count_links
from exchanges.models import Exchange

from .models import Post


def books_of(user):
    """کتاب‌هایی که کاربر داشته، داده یا گرفته؛ فقط برای این‌ها می‌شه معرفی به کتاب وصل کرد."""
    ids = set(Book.objects.filter(owner=user).values_list("id", flat=True))
    ids |= set(Exchange.objects.filter(Q(owner=user) | Q(requester=user), status=Exchange.Status.COMPLETED).values_list("book_id", flat=True))
    return Book.objects.filter(id__in=ids).order_by("title")


class PostForm(PersianFormMixin, forms.ModelForm):
    tags_text = forms.CharField(required=False, max_length=200, label="برچسب‌ها", help_text="تا ۵ برچسب، با ویرگول جدا کن؛ مثل: رمان، کلاسیک",
                                widget=forms.TextInput(attrs={"autocomplete": "off"}))

    class Meta:
        model = Post
        fields = ["title", "book", "book_title", "book_author", "category", "rating", "cover", "body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 14, "placeholder": "چرا این کتاب رو دوست داشتی (یا نداشتی)؟ برای کسی که هنوز نخونده بنویس…", "data-editor": ""}),
            "rating": forms.Select(choices=[("", "بدون امتیاز")] + [(i, f"{'★' * i} ({i})") for i in range(1, 6)]),
        }
        labels = {"book": "کتاب تو هم‌ورق", "book_title": "یا عنوان کتاب", "book_author": "نویسنده‌ی کتاب", "rating": "امتیاز تو"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["book"].queryset = books_of(user) if user else Book.objects.none()
        self.fields["book"].required = False
        self.fields["book"].empty_label = "کتاب من تو هم‌ورق نیست"
        self.fields["book"].help_text = "اگه کتاب رو تو هم‌ورق داشتی یا گرفتی انتخابش کن؛ وگرنه عنوان و نویسنده‌اش رو بنویس."
        self.fields["book"].widget.attrs.update({"data-combobox": "", "data-placeholder": "جستجوی کتاب…"})
        self.fields["category"].widget.attrs.update({"data-combobox": "", "data-placeholder": "جستجوی دسته…"})
        self.fields["category"].queryset = Category.objects.all()
        self.fields["rating"].required = False
        self.fields["body"].help_text = "قالب‌ها: **پررنگ**، *مورب*، ## تیتر، > نقل‌قول، - فهرست، [متن](لینک)"
        if self.instance.pk:
            self.initial["tags_text"] = "، ".join(self.instance.tags.values_list("name", flat=True))

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if "http://" in title or "https://" in title or "www." in title:
            raise forms.ValidationError("عنوان نباید لینک داشته باشه.")
        return title

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if len(body) < settings.POST_MIN_LENGTH:
            raise forms.ValidationError(f"متن خیلی کوتاهه؛ حداقل {settings.POST_MIN_LENGTH} نویسه بنویس تا به درد خواننده بخوره.")
        from .services import is_trusted

        if self.user and not is_trusted(self.user) and count_links(body) > settings.POST_MAX_LINKS_NEW:
            raise forms.ValidationError(f"تا وقتی نوشته‌ی تأییدشده نداری، حداکثر {settings.POST_MAX_LINKS_NEW} لینک مجازه.")
        return body

    def clean_cover(self):
        cover = self.cleaned_data.get("cover")
        if isinstance(cover, UploadedFile):
            if cover.size > 5 * 1024 * 1024:
                raise forms.ValidationError("حجم عکس باید کمتر از ۵ مگابایت باشه.")
            return process_upload(cover, max_side=1600)
        return cover

    def clean(self):
        data = super().clean()
        if not data.get("book") and not (data.get("book_title", "").strip() and data.get("book_author", "").strip()):
            self.add_error("book_title", "کتاب رو انتخاب کن یا عنوان و نویسنده‌اش رو بنویس.")
        if data.get("book"):
            data["book_title"] = data["book_author"] = ""
        if self.user and self.cleaned_data.get("title") and not self.instance.pk:
            from datetime import timedelta

            from django.utils import timezone

            if Post.objects.filter(author=self.user, title=data["title"], created_at__gte=timezone.now() - timedelta(days=7)).exists():
                self.add_error("title", "این عنوان رو تازه ثبت کردی.")
        return data

    def save(self, commit=True):
        post = super().save(commit=commit)
        if commit:
            post.set_tags_from_text(self.cleaned_data.get("tags_text", ""))
        return post
