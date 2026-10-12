from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from common.richtext import plain


class Announcement(models.Model):
    class Kind(models.TextChoices):
        BOOK_FAIR = "book_fair", "نمایشگاه کتاب"
        LAUNCH = "launch", "رونمایی کتاب"
        CRITIQUE = "critique", "نشست نقد و گفتگو"
        READING_CLUB = "reading_club", "کتاب‌خوانی جمعی"
        WORKSHOP = "workshop", "کارگاه و دوره"
        CONTEST = "contest", "مسابقه و فراخوان"
        NEWS = "news", "خبر"
        OTHER = "other", "سایر"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار تأیید"
        PUBLISHED = "published", "منتشرشده"
        REJECTED = "rejected", "ردشده"

    title = models.CharField(max_length=140, verbose_name="عنوان")
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.OTHER, db_index=True, verbose_name="نوع")
    summary = models.CharField(max_length=300, verbose_name="خلاصه")
    body = models.TextField(max_length=8000, blank=True, verbose_name="توضیحات")
    starts_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="شروع")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="پایان")
    is_online = models.BooleanField(default=False, verbose_name="آنلاین")
    city = models.ForeignKey("common.City", null=True, blank=True, on_delete=models.SET_NULL, related_name="announcements", verbose_name="شهر")
    venue = models.CharField(max_length=160, blank=True, verbose_name="محل برگزاری")
    address = models.CharField(max_length=250, blank=True, verbose_name="نشانی")
    link = models.URLField(blank=True, verbose_name="لینک ثبت‌نام یا اطلاعات بیشتر")
    cover = models.ImageField(upload_to="announcements/%Y/%m/", blank=True, verbose_name="تصویر")
    organizer = models.CharField(max_length=120, blank=True, verbose_name="برگزارکننده")
    is_free = models.BooleanField(default=True, verbose_name="رایگان")
    price_note = models.CharField(max_length=120, blank=True, verbose_name="هزینه / توضیح")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="announcements", verbose_name="ثبت‌کننده")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name="وضعیت")
    reject_reason = models.CharField(max_length=300, blank=True, verbose_name="دلیل رد")
    is_featured = models.BooleanField(default=False, verbose_name="ویژه")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان انتشار")
    view_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="بازدید")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        ordering = ["starts_at", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__isnull=True) | Q(starts_at__isnull=True) | Q(ends_at__gte=models.F("starts_at")), name="announcement_end_after_start"),
        ]
        verbose_name = "اطلاعیه"
        verbose_name_plural = "اطلاعیه‌ها"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("announcements:detail", args=[self.pk, slugify(self.title, allow_unicode=True)[:60] or "event"])

    @property
    def is_news(self):
        return self.kind == self.Kind.NEWS

    @property
    def end_moment(self):
        """پایان رویداد برای تشخیص «گذشته»؛ بدون پایان، پایان همون روز شروع حساب می‌شه."""
        if self.ends_at:
            return self.ends_at
        if self.starts_at:
            return self.starts_at.replace(hour=23, minute=59, second=59)
        return None

    @property
    def is_past(self):
        end = self.end_moment
        return bool(end and end < timezone.now())

    @property
    def place_label(self):
        if self.is_online:
            return "آنلاین"
        parts = [p for p in (self.venue, self.city.name if self.city_id else "") if p]
        return "، ".join(parts)

    @property
    def excerpt(self):
        return plain(self.summary, 200)


class AnnouncementBookmark(models.Model):
    """«یادآوری»: کاربر می‌خواد قبل از رویداد بهش خبر بدیم."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="announcement_bookmarks", verbose_name="کاربر")
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="bookmarks", verbose_name="اطلاعیه")
    reminded = models.BooleanField(default=False, verbose_name="یادآوری فرستاده شد")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "announcement"], name="uniq_announcement_bookmark")]
        verbose_name = "یادآوری اطلاعیه"
        verbose_name_plural = "یادآوری‌های اطلاعیه"
