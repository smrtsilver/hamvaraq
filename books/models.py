from django.conf import settings
from django.db import models

from common.text import normalize, work_key


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True, verbose_name="نام دسته")

    class Meta:
        ordering = ["name"]
        verbose_name = "دسته"
        verbose_name_plural = "دسته‌ها"

    def __str__(self):
        return self.name


class Book(models.Model):
    class Condition(models.TextChoices):
        NEW = "new", "نو"
        USED = "used", "دست‌دوم"

    class Status(models.TextChoices):
        AVAILABLE = "available", "موجود"
        RESERVED = "reserved", "رزرو"
        EXCHANGED = "exchanged", "مبادله‌شده"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="books", verbose_name="صاحب")
    title = models.CharField(max_length=200, verbose_name="عنوان")
    author = models.CharField(max_length=150, verbose_name="نویسنده")
    isbn = models.CharField(max_length=20, blank=True, verbose_name="شابک")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="books", verbose_name="دسته")
    condition = models.CharField(max_length=8, choices=Condition.choices, default=Condition.USED, verbose_name="وضعیت فیزیکی")
    city = models.ForeignKey("common.City", on_delete=models.PROTECT, related_name="books", verbose_name="شهر")
    cover = models.ImageField(upload_to="books/%Y/%m/", blank=True, verbose_name="عکس")
    cover_thumb = models.ImageField(upload_to="books/thumbs/%Y/%m/", blank=True, editable=False, verbose_name="بند‌انگشتی")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True, verbose_name="وضعیت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    # فیلدهای کمکی جستجو؛ خودکار از عنوان/نویسنده/شابک ساخته می‌شن
    search_text = models.TextField(blank=True, editable=False, verbose_name="متن جستجو")
    work_key = models.CharField(max_length=400, blank=True, db_index=True, editable=False, verbose_name="کلید کتاب")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "کتاب"
        verbose_name_plural = "کتاب‌ها"

    def __str__(self):
        return self.title

    @property
    def thumb_url(self):
        """بند‌انگشتی برای گرید؛ اگه نداشت (کتاب قدیمی) خود عکس."""
        if self.cover_thumb:
            return self.cover_thumb.url
        return self.cover.url if self.cover else ""

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("books:detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if self.cover and not self.cover._committed:
            # عکس تازه آپلود شده: بند‌انگشتی بسازیم (کاور قبلاً تو فرم پردازش شده)
            from common.images import make_thumb

            self.cover_thumb = make_thumb(self.cover.file)
            self.cover.file.seek(0)
        elif not self.cover:
            self.cover_thumb = ""
        self.search_text = normalize(f"{self.title} {self.author} {self.isbn}")
        self.work_key = work_key(self.title, self.author)
        fields = kwargs.get("update_fields")
        if fields is not None and ({"title", "author", "isbn"} & set(fields)):
            kwargs["update_fields"] = {*fields, "search_text", "work_key"}
        super().save(*args, **kwargs)


class BookPhoto(models.Model):
    """عکس‌های اضافه‌ی کتاب (به‌جز عکس اصلی)."""

    MAX_EXTRA = 4

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="photos", verbose_name="کتاب")
    image = models.ImageField(upload_to="books/%Y/%m/", verbose_name="عکس")
    position = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "عکس کتاب"
        verbose_name_plural = "عکس‌های کتاب"


class Wishlist(models.Model):
    """کاربر عنوان، نویسنده یا شابک کتابی رو که می‌خواد ثبت می‌کنه."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishes", verbose_name="کاربر")
    text = models.CharField(max_length=200, verbose_name="عنوان، نویسنده یا شابک")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "text"], name="uniq_wish")]
        ordering = ["-created_at"]
        verbose_name = "آرزو"
        verbose_name_plural = "لیست آرزو"

    def __str__(self):
        return self.text


class BookNote(models.Model):
    """یادداشت صاحب قبلی برای خواننده‌ی بعدی."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="notes", verbose_name="کتاب")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="book_notes", verbose_name="نویسنده")
    exchange = models.OneToOneField("exchanges.Exchange", null=True, blank=True, on_delete=models.SET_NULL, related_name="note", verbose_name="مبادله")
    text = models.CharField(max_length=500, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "یادداشت کتاب"
        verbose_name_plural = "یادداشت‌های کتاب"


class BookJourney(models.Model):
    """هر مبادله‌ی کامل‌شده یه قدم از مسیر کتابه."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="journey", verbose_name="کتاب")
    exchange = models.OneToOneField("exchanges.Exchange", on_delete=models.CASCADE, related_name="journey_step", verbose_name="مبادله")
    from_city = models.ForeignKey("common.City", null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="شهر مبدأ")
    to_city = models.ForeignKey("common.City", null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="شهر مقصد")
    date = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ")

    class Meta:
        ordering = ["date"]
        verbose_name = "مسیر کتاب"
        verbose_name_plural = "مسیر کتاب‌ها"


class Review(models.Model):
    """نقد و ستاره؛ فقط کسی که کتاب رو از طریق یه مبادله‌ی کامل‌شده گرفته می‌تونه بنویسه."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews", verbose_name="کتاب")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews", verbose_name="کاربر")
    stars = models.PositiveSmallIntegerField(choices=[(i, f"{i} ستاره") for i in range(1, 6)], verbose_name="ستاره")
    text = models.TextField(blank=True, max_length=1500, verbose_name="نقد")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["book", "user"], name="one_review_per_user_book"),
            models.CheckConstraint(condition=models.Q(stars__gte=1, stars__lte=5), name="review_stars_1_5"),
        ]
        ordering = ["-created_at"]
        verbose_name = "نقد"
        verbose_name_plural = "نقدها"
