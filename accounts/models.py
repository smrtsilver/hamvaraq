from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        RESTRICTED = "restricted", "محدود"
        BANNED = "banned", "مسدود"

    # ایمیل اختیاریه و فقط برای بازیابی رمز استفاده می‌شه
    city = models.ForeignKey(
        "common.City", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="users", verbose_name="شهر",
    )
    points = models.IntegerField(default=0, verbose_name="امتیاز")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, verbose_name="وضعیت")
    restricted_until = models.DateTimeField(null=True, blank=True, verbose_name="محدودیت تا")
    warnings = models.PositiveIntegerField(default=0, verbose_name="تعداد اخطار")
    # کنترل سوءاستفاده از امتیاز اولیه؛ هش آی‌پی (نه خود آی‌پی)، accounts/ip.py
    signup_ip_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False, verbose_name="هش شبکه‌ی ثبت‌نام")
    last_ip_hash = models.CharField(max_length=64, blank=True, editable=False, verbose_name="هش شبکه‌ی آخرین ورود")
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="زمان حذف حساب")
    welcome_granted = models.BooleanField(default=False, verbose_name="امتیاز خوش‌آمد گرفته")

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربرها"

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    @property
    def is_restricted(self):
        """محدودیت موقت: فقط کتاب می‌ده، نمی‌تونه کتاب بگیره."""
        if self.status != self.Status.RESTRICTED:
            return False
        return self.restricted_until is None or self.restricted_until > timezone.now()

    def is_linked_to(self, other):
        """دو حساب که از یه شبکه (آی‌پی) وارد شدن (ثبت‌نام یا آخرین ورود)."""
        mine = {h for h in (self.signup_ip_hash, self.last_ip_hash) if h}
        theirs = {h for h in (other.signup_ip_hash, other.last_ip_hash) if h}
        return bool(mine & theirs)

    @property
    def can_request(self):
        return self.is_active and self.status != self.Status.BANNED and not self.is_restricted


class Badge(models.Model):
    code = models.SlugField(unique=True, verbose_name="کد")
    name = models.CharField(max_length=60, verbose_name="نام")
    description = models.CharField(max_length=200, verbose_name="توضیح")

    class Meta:
        verbose_name = "نشان"
        verbose_name_plural = "نشان‌ها"

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_badges", verbose_name="کاربر")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="user_badges", verbose_name="نشان")
    awarded_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان دریافت")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "badge"], name="uniq_user_badge")]
        ordering = ["awarded_at"]
        verbose_name = "نشان کاربر"
        verbose_name_plural = "نشان‌های کاربر"


class PointEntry(models.Model):
    """دفتر امتیاز: هر تغییر امتیاز یک ردیف؛ مجموع delta ها همیشه برابر User.points است (common/points.py)."""

    class Reason(models.TextChoices):
        OPENING = "opening", "موجودی اولیه"
        WELCOME = "welcome", "هدیه‌ی ثبت‌نام"
        REQUEST_HOLD = "request_hold", "نگه‌داشتن امتیاز درخواست"
        REQUEST_REFUND = "request_refund", "برگشت امتیاز درخواست"
        EXCHANGE_REWARD = "exchange_reward", "پاداش مبادله‌ی موفق"
        ADMIN_ADJUST = "admin_adjust", "تغییر توسط مدیریت"
        RECONCILE = "reconcile", "اصلاح دفتر"

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="point_entries", verbose_name="کاربر")
    delta = models.IntegerField(verbose_name="تغییر")
    reason = models.CharField(max_length=20, choices=Reason.choices, verbose_name="دلیل")
    exchange = models.ForeignKey("exchanges.Exchange", null=True, blank=True, on_delete=models.PROTECT, related_name="point_entries", verbose_name="مبادله")
    note = models.CharField(max_length=200, blank=True, verbose_name="توضیح")
    balance_after = models.IntegerField(verbose_name="موجودی بعد از تغییر")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="زمان")

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["user", "-id"])]
        verbose_name = "ردیف دفتر امتیاز"
        verbose_name_plural = "دفتر امتیاز"

    def __str__(self):
        return f"{self.user} {self.delta:+d} ({self.get_reason_display()})"


class Follow(models.Model):
    """دنبال کردن یه کتاب‌خوان؛ فقط فید رو پر می‌کنه (اعلانی فرستاده نمی‌شه)."""

    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name="following_set", verbose_name="دنبال‌کننده")
    followee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follower_set", verbose_name="دنبال‌شونده")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["follower", "followee"], name="one_follow"),
                       models.CheckConstraint(condition=~models.Q(follower=models.F("followee")), name="no_self_follow")]
        indexes = [models.Index(fields=["followee", "-created_at"])]
        verbose_name = "دنبال کردن"
        verbose_name_plural = "دنبال کردن‌ها"
