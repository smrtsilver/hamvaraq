from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        EXCHANGE = "exchange", "مبادله"
        CHAT = "chat", "پیام"
        WISHLIST = "wishlist", "لیست آرزو"
        BADGE = "badge", "نشان"
        REPORT = "report", "گزارش"
        EVENT = "event", "اطلاعیه"
        SYSTEM = "system", "سیستم"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", verbose_name="کاربر")
    text = models.CharField(max_length=300, verbose_name="متن")
    url = models.CharField(max_length=300, blank=True, verbose_name="لینک")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SYSTEM, verbose_name="نوع")
    is_read = models.BooleanField(default=False, verbose_name="خوانده شده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "اعلان"
        verbose_name_plural = "اعلان‌ها"

    def __str__(self):
        return self.text[:40]


class PushSubscription(models.Model):
    """اشتراک اعلان مرورگر (Web Push) یک دستگاه."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions", verbose_name="کاربر")
    endpoint = models.CharField(max_length=700, unique=True, verbose_name="آدرس")
    p256dh = models.CharField(max_length=200, verbose_name="کلید عمومی")
    auth = models.CharField(max_length=100, verbose_name="کلید احراز")
    user_agent = models.CharField(max_length=200, blank=True, verbose_name="دستگاه")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name="آخرین ارسال موفق")
    failures = models.PositiveSmallIntegerField(default=0, verbose_name="تعداد خطای پیاپی")

    class Meta:
        verbose_name = "اشتراک اعلان مرورگر"
        verbose_name_plural = "اشتراک‌های اعلان مرورگر"

    def __str__(self):
        return f"{self.user} — {self.user_agent[:30]}"


class NotificationPreference(models.Model):
    """اعلان داخل سایت همیشه فعاله؛ این‌ها فقط اعلان بیرون از سایت (Web Push) رو کنترل می‌کنن."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_prefs", verbose_name="کاربر")
    push_exchange = models.BooleanField(default=True, verbose_name="درخواست‌ها و وضعیت مبادله‌ها")
    push_chat = models.BooleanField(default=True, verbose_name="پیام‌های چت")
    push_wishlist = models.BooleanField(default=True, verbose_name="ثبت کتاب‌های لیست آرزو")
    push_other = models.BooleanField(default=True, verbose_name="نشان‌ها، اطلاعیه‌ها و بقیه")

    class Meta:
        verbose_name = "ترجیحات اعلان"
        verbose_name_plural = "ترجیحات اعلان"

    def __str__(self):
        return f"ترجیحات {self.user}"

    FIELD_BY_KIND = {"exchange": "push_exchange", "chat": "push_chat", "wishlist": "push_wishlist"}

    @classmethod
    def allows(cls, user, kind):
        """کاربری که ترجیحاتی ثبت نکرده همه‌چیز رو می‌گیره."""
        prefs = cls.objects.filter(user=user).first()
        return True if prefs is None else getattr(prefs, cls.FIELD_BY_KIND.get(kind, "push_other"))
