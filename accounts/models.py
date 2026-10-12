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
    signup_ip_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    last_ip_hash = models.CharField(max_length=64, blank=True, editable=False)
    welcome_granted = models.BooleanField(default=False, verbose_name="امتیاز خوش‌آمد گرفته")

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربرها"

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
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=60, verbose_name="نام")
    description = models.CharField(max_length=200, verbose_name="توضیح")

    class Meta:
        verbose_name = "نشان"
        verbose_name_plural = "نشان‌ها"

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="user_badges")
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "badge"], name="uniq_user_badge")]
        ordering = ["awarded_at"]
        verbose_name = "نشان کاربر"
        verbose_name_plural = "نشان‌های کاربر"
