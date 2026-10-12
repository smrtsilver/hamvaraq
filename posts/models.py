import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from common.richtext import plain
from common.text import normalize


RESERVED_SLUGS = {"new", "mine", "preview", "by"}  # با مسیرهای ثابت تداخل نکنه


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True, verbose_name="برچسب")

    class Meta:
        ordering = ["name"]
        verbose_name = "برچسب"
        verbose_name_plural = "برچسب‌ها"

    def __str__(self):
        return self.name


class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PENDING = "pending", "در انتظار تأیید"
        PUBLISHED = "published", "منتشرشده"
        REJECTED = "rejected", "ردشده"

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts", verbose_name="نویسنده")
    title = models.CharField(max_length=140, verbose_name="عنوان")
    slug = models.SlugField(max_length=170, unique=True, allow_unicode=True, editable=False, verbose_name="نشانی")
    book = models.ForeignKey("books.Book", null=True, blank=True, on_delete=models.SET_NULL, related_name="posts", verbose_name="کتاب مرتبط")
    book_title = models.CharField(max_length=200, blank=True, verbose_name="عنوان کتاب")
    book_author = models.CharField(max_length=150, blank=True, verbose_name="نویسنده‌ی کتاب")
    body = models.TextField(max_length=12000, verbose_name="متن")
    cover = models.ImageField(upload_to="posts/%Y/%m/", blank=True, verbose_name="تصویر")
    rating = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="امتیاز شخصی")
    category = models.ForeignKey("books.Category", null=True, blank=True, on_delete=models.SET_NULL, related_name="posts", verbose_name="دسته")
    tags = models.ManyToManyField(Tag, blank=True, related_name="posts", verbose_name="برچسب‌ها")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="وضعیت")
    reject_reason = models.CharField(max_length=300, blank=True, verbose_name="دلیل رد")
    is_featured = models.BooleanField(default=False, verbose_name="ویژه")
    published_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="زمان انتشار")
    search_text = models.TextField(blank=True, editable=False)
    view_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="بازدید")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    class Meta:
        ordering = ["-published_at", "-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(rating__isnull=True) | models.Q(rating__gte=1, rating__lte=5), name="post_rating_1_5")]
        verbose_name = "معرفی کتاب"
        verbose_name_plural = "معرفی‌های کتاب"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.search_text = normalize(f"{self.title} {self.book_title} {self.book_author} {self.book.title if self.book_id else ''} {self.body[:3000]}")
        fields = kwargs.get("update_fields")
        if fields is not None:
            kwargs["update_fields"] = {*fields, "search_text"}
        if not self.slug:
            base = slugify(self.title, allow_unicode=True)[:120] or "post"
            if base in RESERVED_SLUGS:
                base += "-post"
            slug, n = base, 1
            while Post.objects.filter(slug=slug).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("posts:detail", args=[self.slug])

    @property
    def display_book_title(self):
        return self.book.title if self.book_id else self.book_title

    @property
    def display_book_author(self):
        return self.book.author if self.book_id else self.book_author

    @property
    def excerpt(self):
        return plain(self.body, 200)

    @property
    def reading_minutes(self):
        return max(1, round(len(self.body.split()) / 180))

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED and (self.published_at is None or self.published_at <= timezone.now())

    def set_tags_from_text(self, text):
        """برچسب‌ها: جداشده با ویرگول فارسی/انگلیسی؛ حداکثر ۵ تا، نرمال‌شده و بدون تکرار."""
        names, seen = [], set()
        for raw in re.split(r"[,،\n]", text or ""):
            name = " ".join(raw.split())[:40]
            key = normalize(name)
            if name and key not in seen:
                seen.add(key)
                names.append(name)
        tags = []
        for name in names[:5]:
            existing = next((t for t in Tag.objects.all() if normalize(t.name) == normalize(name)), None)
            tags.append(existing or Tag.objects.create(name=name))
        self.tags.set(tags)
