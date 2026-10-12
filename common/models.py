from django.conf import settings
from django.db import models


class Province(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="نام استان")

    class Meta:
        ordering = ["name"]
        verbose_name = "استان"
        verbose_name_plural = "استان‌ها"

    def __str__(self):
        return self.name


class City(models.Model):
    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name="cities", verbose_name="استان")
    name = models.CharField(max_length=100, verbose_name="نام شهر")

    class Meta:
        ordering = ["name"]
        verbose_name = "شهر"
        verbose_name_plural = "شهرها"
        constraints = [models.UniqueConstraint(fields=["province", "name"], name="unique_city_per_province")]

    def __str__(self):
        return self.name

    @property
    def full_name(self):
        """«شهر، استان»؛ برای شهرهای هم‌نام (مثل خرم‌آباد) ضروریه."""
        return f"{self.name}، {self.province.name}"


class MeetingPoint(models.Model):
    """نقطه‌ی تحویل عمومی و امن (ایستگاه مترو، کافه، کتابخونه…) که ادمین تعریف می‌کنه."""

    class Kind(models.TextChoices):
        METRO = "metro", "ایستگاه مترو"
        CAFE = "cafe", "کافه"
        LIBRARY = "library", "کتابخانه"
        UNIVERSITY = "university", "دانشگاه"
        OTHER = "other", "سایر"

    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="meeting_points", verbose_name="شهر")
    name = models.CharField(max_length=120, verbose_name="نام")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.OTHER, verbose_name="نوع")
    address = models.CharField(max_length=250, blank=True, verbose_name="نشانی")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = ["city__name", "kind", "name"]
        verbose_name = "نقطه‌ی تحویل"
        verbose_name_plural = "نقاط تحویل"

    def __str__(self):
        return f"{self.get_kind_display()} {self.name} ({self.city})"


class SiteSetting(models.Model):
    """تنظیمات تک‌رکوردی سایت: متن لندینگ، فوتر و شبکه‌های اجتماعی؛ بدون دیپلوی از ادمین قابل تغییره."""

    tagline = models.CharField(max_length=120, default="بخوان، بسپار، دوباره بخوان", verbose_name="شعار")
    hero_title = models.CharField(max_length=200, default="کتاب‌ها برای خوانده‌شدن‌اند، نه ماندن روی قفسه",
                                  verbose_name="تیتر اصلی لندینگ")
    hero_subtitle = models.TextField(
        default="هم‌ورق جاییه که کتاب‌خوان‌ها کتاب‌هاشون رو رایگان دست‌به‌دست می‌کنن. کتابی که خوندی رو بسپار، کتاب بعدیت رو بگیر؛ بدون پول، فقط با امتیاز.",
        verbose_name="زیرعنوان لندینگ")
    cta_title = models.CharField(max_length=200, default="هم‌ورق شو", verbose_name="تیتر دعوت پایانی")
    cta_text = models.TextField(default="ثبت‌نام رایگانه و ۱ امتیاز هدیه داره؛ همین الان اولین کتابت رو بگیر.",
                                verbose_name="متن دعوت پایانی")
    footer_text = models.CharField(max_length=300, default="هم‌ورق؛ مبادله‌ی رایگان کتاب بین کتاب‌خوان‌ها.", verbose_name="متن فوتر")
    telegram_url = models.URLField(blank=True, verbose_name="کانال تلگرام")
    instagram_url = models.URLField(blank=True, verbose_name="اینستاگرام")
    contact_email = models.EmailField(blank=True, verbose_name="ایمیل تماس")
    banner_text = models.CharField(max_length=200, blank=True, verbose_name="متن بنر بالای سایت")
    banner_url = models.CharField(max_length=300, blank=True, verbose_name="لینک بنر")
    banner_active = models.BooleanField(default=False, verbose_name="بنر نمایش داده شود")

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self):
        return "تنظیمات سایت"

    def save(self, *args, **kwargs):
        self.pk = 1  # فقط یک رکورد
        super().save(*args, **kwargs)
        SiteSetting._cache = None

    @classmethod
    def load(cls):
        """رکورد تنظیمات (در صورت نبود با مقدارهای پیش‌فرض ساخته می‌شه). تا ۳۰ ثانیه تو حافظه نگه داشته می‌شه."""
        import time

        cached = getattr(cls, "_cache", None)
        if cached and time.monotonic() - cached[0] < 30:
            return cached[1]
        obj, _ = cls.objects.get_or_create(pk=1)
        cls._cache = (time.monotonic(), obj)
        return obj


class AuditLog(models.Model):
    """ثبت اقدام‌های مدیریتی پنل: چه کسی، چه کاری، روی چی و چرا."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", verbose_name="مدیر")
    action = models.CharField(max_length=80, verbose_name="اقدام")
    target = models.CharField(max_length=200, blank=True, verbose_name="روی")
    note = models.CharField(max_length=300, blank=True, verbose_name="توضیح")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "لاگ مدیریت"
        verbose_name_plural = "لاگ‌های مدیریت"

    def __str__(self):
        return f"{self.actor}: {self.action} {self.target}"
