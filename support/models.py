from django.conf import settings
from django.db import models
from django.urls import reverse


class Ticket(models.Model):
    class Category(models.TextChoices):
        BUG = "bug", "خطا یا مشکل فنی در سایت"
        ACCOUNT = "account", "مشکل حساب کاربری"
        EXCHANGE = "exchange", "مشکل در یک مبادله"
        CONTENT = "content", "محتوای نامناسب"
        SUGGESTION = "suggestion", "پیشنهاد"
        OTHER = "other", "سایر"

    class Status(models.TextChoices):
        NEW = "new", "جدید"
        IN_PROGRESS = "in_progress", "در حال بررسی"
        RESOLVED = "resolved", "حل‌شده"
        CLOSED = "closed", "بسته‌شده"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets", verbose_name="کاربر")
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.BUG, verbose_name="موضوع")
    subject = models.CharField(max_length=100, verbose_name="عنوان")
    message = models.TextField(max_length=3000, verbose_name="شرح مشکل")
    page_url = models.CharField(max_length=300, blank=True, verbose_name="صفحه‌ی مرتبط")
    contact = models.CharField(max_length=120, blank=True, verbose_name="راه تماس (اختیاری)")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True, verbose_name="وضعیت")
    reply = models.TextField(max_length=2000, blank=True, verbose_name="پاسخ مدیریت")
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="رسیدگی‌کننده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "گزارش مشکل"
        verbose_name_plural = "گزارش‌های مشکل"

    def __str__(self):
        return f"#{self.pk} {self.subject}"

    def get_absolute_url(self):
        return reverse("support:detail", args=[self.pk])

    @property
    def is_open(self):
        return self.status in (self.Status.NEW, self.Status.IN_PROGRESS)
