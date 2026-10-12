from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", verbose_name="کاربر")
    text = models.CharField(max_length=300, verbose_name="متن")
    url = models.CharField(max_length=300, blank=True, verbose_name="لینک")
    is_read = models.BooleanField(default=False, verbose_name="خوانده شده")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "اعلان"
        verbose_name_plural = "اعلان‌ها"

    def __str__(self):
        return self.text[:40]
