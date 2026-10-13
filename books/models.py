from django.conf import settings
from django.db import models

from common.text import first_author, normalize, slugify_fa, work_key


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True, verbose_name="نام دسته")

    class Meta:
        ordering = ["name"]
        verbose_name = "دسته"
        verbose_name_plural = "دسته‌ها"

    def __str__(self):
        return self.name


class Edition(models.Model):
    """
    «چاپ» یک کتاب بر اساس ISBN-13 (ISBN-10 هم‌ارزش به همون تبدیل می‌شه). فیلدهای عنوان/نویسنده‌ی خود Book برای
    سازگاری عقب‌رو می‌مونن؛ Book.edition اختیاریه. منبع داده: nlai/openlibrary/google (ادغام‌شده) یا user.
    داده‌ی کاربر هیچ‌وقت داده‌ی منبع‌دار رو بازنویسی نمی‌کنه (ضد مسموم‌سازی)؛ تأیید دو کاربر مستقل اطمینان رو بالا می‌بره.
    """

    SOURCE_USER = "user"

    isbn13 = models.CharField(max_length=13, unique=True, null=True, blank=True, verbose_name="شابک ۱۳رقمی")
    title = models.CharField(max_length=300, verbose_name="عنوان")
    subtitle = models.CharField(max_length=300, blank=True, verbose_name="زیرعنوان")
    authors = models.JSONField(default=list, blank=True, verbose_name="نویسنده‌ها")
    translators = models.JSONField(default=list, blank=True, verbose_name="مترجم‌ها")
    publisher = models.CharField(max_length=200, blank=True, verbose_name="ناشر")
    publisher_slug = models.CharField(max_length=120, blank=True, db_index=True, editable=False, verbose_name="نشانی ناشر")
    year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="سال انتشار")
    year_calendar = models.CharField(max_length=10, blank=True, choices=[("jalali", "شمسی"), ("gregorian", "میلادی")], verbose_name="تقویم سال")
    edition_no = models.CharField(max_length=50, blank=True, verbose_name="نوبت چاپ")
    volume = models.CharField(max_length=50, blank=True, verbose_name="جلد")
    pages = models.PositiveIntegerField(null=True, blank=True, verbose_name="تعداد صفحه")
    language = models.CharField(max_length=20, blank=True, verbose_name="زبان")
    subjects = models.JSONField(default=list, blank=True, verbose_name="موضوع‌ها")
    description = models.TextField(blank=True, verbose_name="توضیح")
    cover_url = models.URLField(max_length=500, blank=True, verbose_name="نشانی جلد")
    source = models.CharField(max_length=40, default="user", db_index=True, verbose_name="منبع")
    provenance = models.JSONField(default=dict, blank=True, verbose_name="سابقه‌ی داده")
    confidence = models.PositiveSmallIntegerField(default=20, verbose_name="اطمینان")
    verified = models.BooleanField(default=False, verbose_name="تأییدشده توسط مدیر")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="ثبت‌کننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "چاپ کتاب"
        verbose_name_plural = "چاپ‌های کتاب"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.publisher_slug = slugify_fa(self.publisher)
        fields = kwargs.get("update_fields")
        if fields is not None and "publisher" in fields:
            kwargs["update_fields"] = {*fields, "publisher_slug"}
        super().save(*args, **kwargs)

    @property
    def author_line(self):
        return "، ".join(self.authors)

    @property
    def is_source_backed(self):
        return self.source != self.SOURCE_USER


class VisibleBookManager(models.Manager):
    """
    مدیر پیش‌فرض: فقط کتاب‌هایی که باید تو سایت دیده بشن (حذف‌نشده، صاحب فعال و غیرمسدود).
    ادمین و پنل از Book.all_objects استفاده می‌کنن و دسترسی FK مثل Exchange.book از مدیر ساده‌ی پایه می‌گذره؛
    پس تاریخچه‌ی مبادله حتی با کتاب پنهان کامل دیده می‌شه.
    """

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True).exclude(owner__is_active=False).exclude(owner__status="banned")


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
    view_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="بازدید یکتا")
    cover = models.ImageField(upload_to="books/%Y/%m/", blank=True, verbose_name="عکس")
    cover_thumb = models.ImageField(upload_to="books/thumbs/%Y/%m/", blank=True, editable=False, verbose_name="بند‌انگشتی")
    # نسخه‌های سبک برای srcset/<picture> (WebP)، ابعاد واقعی (برای width/height و CLS صفر) و LQIP
    cover_webp = models.ImageField(upload_to="books/webp/%Y/%m/", blank=True, editable=False, verbose_name="WebP بزرگ")
    cover_thumb_webp = models.ImageField(upload_to="books/webp/%Y/%m/", blank=True, editable=False, verbose_name="WebP کوچک")
    cover_w = models.PositiveSmallIntegerField(null=True, blank=True, editable=False, verbose_name="عرض جلد")
    cover_h = models.PositiveSmallIntegerField(null=True, blank=True, editable=False, verbose_name="ارتفاع جلد")
    cover_lqip = models.CharField(max_length=900, blank=True, editable=False, verbose_name="پیش‌نمایش مات")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    edition = models.ForeignKey(Edition, null=True, blank=True, on_delete=models.PROTECT, related_name="books", verbose_name="چاپ")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True, verbose_name="وضعیت")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False, verbose_name="زمان حذف")
    # فیلدهای کمکی جستجو؛ خودکار از عنوان/نویسنده/شابک ساخته می‌شن
    search_text = models.TextField(blank=True, editable=False, verbose_name="متن جستجو")
    work_key = models.CharField(max_length=400, blank=True, db_index=True, editable=False, verbose_name="کلید کتاب")
    author_slug = models.CharField(max_length=120, blank=True, db_index=True, editable=False, verbose_name="نشانی نویسنده")

    objects = VisibleBookManager()
    all_objects = models.Manager()

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

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def build_cover_variants(self):
        """WebP (۹۶۰ و ۴۲۰)، ابعاد و LQIP از روی فایل جلد؛ خطای تصویر سیو کتاب رو خراب نمی‌کنه (همون JPEG کار می‌کنه)."""
        import logging

        from common.images import WEBP_MAIN, WEBP_THUMB, image_size, make_lqip, make_webp

        try:
            f = self.cover.file
            self.cover_w, self.cover_h = image_size(f)
            self.cover_lqip = make_lqip(f)
            self.cover_webp = make_webp(f, WEBP_MAIN)
            self.cover_thumb_webp = make_webp(f, WEBP_THUMB, quality=75)
        except Exception:      # noqa: BLE001 — فقط بهینه‌سازیه
            logging.getLogger(__name__).exception("cover variants failed for book %s", self.pk)
        finally:
            self.cover.file.seek(0)

    def soft_delete(self):
        """حذف نرم: کتاب از سایت پنهان می‌شه ولی تاریخچه‌ی مبادله، رأی‌ها و نقدها سر جاشون می‌مونن."""
        from django.utils import timezone

        self.deleted_at = timezone.now()
        Book.all_objects.filter(pk=self.pk).update(deleted_at=self.deleted_at)

    def restore(self):
        self.deleted_at = None
        Book.all_objects.filter(pk=self.pk).update(deleted_at=None)

    def save(self, *args, **kwargs):
        if self.cover and not self.cover._committed:
            # عکس تازه آپلود شده: بند‌انگشتی و نسخه‌های WebP/LQIP بسازیم (کاور قبلاً تو فرم پردازش شده)
            from common.images import make_thumb

            self.cover_thumb = make_thumb(self.cover.file)
            self.cover.file.seek(0)
            self.build_cover_variants()
        elif not self.cover:
            self.cover_thumb = self.cover_webp = self.cover_thumb_webp = ""
            self.cover_w = self.cover_h = None
            self.cover_lqip = ""
        self.search_text = normalize(f"{self.title} {self.author} {self.isbn}")
        self.work_key = work_key(self.title, self.author)
        self.author_slug = slugify_fa(first_author(self.author))
        fields = kwargs.get("update_fields")
        if fields is not None and ({"title", "author", "isbn"} & set(fields)):
            kwargs["update_fields"] = {*fields, "search_text", "work_key", "author_slug"}
        super().save(*args, **kwargs)
        if self.isbn and not self.edition_id:
            from .catalog import attach_edition

            attach_edition(self)         # فقط دیتابیس (بدون شبکه)؛ استعلام بیرونی تو API شابک انجام می‌شه


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
    """
    کاربر عنوان، نویسنده یا شابک کتابی رو که می‌خواد ثبت می‌کنه.
    برای تطبیق سریع (بدون اسکن کل جدول): شابک تو فیلد ایندکس‌دار isbn و کلمه‌های معنی‌دار تو WishToken نگه‌داری می‌شن.
    """

    MAX_PER_USER = 30

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishes", verbose_name="کاربر")
    text = models.CharField(max_length=200, verbose_name="عنوان، نویسنده یا شابک")
    isbn = models.CharField(max_length=20, blank=True, db_index=True, editable=False, verbose_name="شابک نرمال")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "text"], name="uniq_wish")]
        ordering = ["-created_at"]
        verbose_name = "آرزو"
        verbose_name_plural = "لیست آرزو"

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        from .isbn import normalize as isbn_normalize

        self.isbn = isbn_normalize(self.text) or ""
        super().save(*args, **kwargs)
        self.rebuild_tokens()

    def rebuild_tokens(self):
        from common.text import significant_words

        words = [] if self.isbn else significant_words(self.text)
        self.tokens.all().delete()
        WishToken.objects.bulk_create([WishToken(wish=self, word=w) for w in words])


class WishToken(models.Model):
    """یک کلمه‌ی معنی‌دار از یه آرزو؛ با ایندکس word کتابِ تازه فقط آرزوهای نامزد رو پیدا می‌کنه."""

    wish = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="tokens")
    word = models.CharField(max_length=60, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["wish", "word"], name="uniq_wish_word")]


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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews", verbose_name="کاربر")
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
