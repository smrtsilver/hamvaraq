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
    description = models.TextField(blank=True, verbose_name="توضیحات")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True, verbose_name="وضعیت")
    created_at = models.DateTimeField(auto_now_add=True)
    # فیلدهای کمکی جستجو؛ خودکار از عنوان/نویسنده/شابک ساخته می‌شن
    search_text = models.TextField(blank=True, editable=False)
    work_key = models.CharField(max_length=400, blank=True, db_index=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "کتاب"
        verbose_name_plural = "کتاب‌ها"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("books:detail", args=[self.pk])

    def save(self, *args, **kwargs):
        self.search_text = normalize(f"{self.title} {self.author} {self.isbn}")
        self.work_key = work_key(self.title, self.author)
        fields = kwargs.get("update_fields")
        if fields is not None and ({"title", "author", "isbn"} & set(fields)):
            kwargs["update_fields"] = {*fields, "search_text", "work_key"}
        super().save(*args, **kwargs)


class Wishlist(models.Model):
    """کاربر عنوان، نویسنده یا شابک کتابی رو که می‌خواد ثبت می‌کنه."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishes")
    text = models.CharField(max_length=200, verbose_name="عنوان، نویسنده یا شابک")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "text"], name="uniq_wish")]
        ordering = ["-created_at"]
        verbose_name = "آرزو"
        verbose_name_plural = "لیست آرزو"

    def __str__(self):
        return self.text


class BookNote(models.Model):
    """یادداشت صاحب قبلی برای خواننده‌ی بعدی."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="book_notes")
    exchange = models.OneToOneField("exchanges.Exchange", null=True, blank=True, on_delete=models.SET_NULL, related_name="note")
    text = models.CharField(max_length=500, verbose_name="یادداشت")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "یادداشت کتاب"
        verbose_name_plural = "یادداشت‌های کتاب"


class BookJourney(models.Model):
    """هر مبادله‌ی کامل‌شده یه قدم از مسیر کتابه."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="journey")
    exchange = models.OneToOneField("exchanges.Exchange", on_delete=models.CASCADE, related_name="journey_step")
    from_city = models.ForeignKey("common.City", null=True, on_delete=models.SET_NULL, related_name="+")
    to_city = models.ForeignKey("common.City", null=True, on_delete=models.SET_NULL, related_name="+")
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        verbose_name = "مسیر کتاب"
        verbose_name_plural = "مسیر کتاب‌ها"


class Review(models.Model):
    """نقد و ستاره؛ فقط کسی که کتاب رو از طریق یه مبادله‌ی کامل‌شده گرفته می‌تونه بنویسه."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    stars = models.PositiveSmallIntegerField(choices=[(i, f"{i} ستاره") for i in range(1, 6)], verbose_name="ستاره")
    text = models.TextField(blank=True, max_length=1500, verbose_name="نقد")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["book", "user"], name="one_review_per_user_book"),
            models.CheckConstraint(condition=models.Q(stars__gte=1, stars__lte=5), name="review_stars_1_5"),
        ]
        ordering = ["-created_at"]
        verbose_name = "نقد"
        verbose_name_plural = "نقدها"
