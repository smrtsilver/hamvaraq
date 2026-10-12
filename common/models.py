from django.db import models


class City(models.Model):
    name = models.CharField(max_length=80, unique=True, verbose_name="نام شهر")

    class Meta:
        ordering = ["name"]
        verbose_name = "شهر"
        verbose_name_plural = "شهرها"

    def __str__(self):
        return self.name


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
