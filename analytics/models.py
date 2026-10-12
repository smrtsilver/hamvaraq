from django.db import models


class ViewLog(models.Model):
    """یک بازدید یکتا: هر بازدیدکننده برای هر مورد فقط یک بار (برای همیشه) شمرده می‌شه."""

    class Kind(models.TextChoices):
        BOOK = "book", "کتاب"
        POST = "post", "معرفی"
        EVENT = "event", "اطلاعیه"

    kind = models.CharField(max_length=8, choices=Kind.choices, verbose_name="نوع")
    object_id = models.PositiveIntegerField(verbose_name="شناسه")
    visitor = models.CharField(max_length=40, verbose_name="بازدیدکننده (هش)")
    is_member = models.BooleanField(default=False, verbose_name="عضو")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "object_id", "visitor"], name="uniq_view_per_visitor")]
        indexes = [models.Index(fields=["kind", "created_at"]), models.Index(fields=["kind", "object_id"])]
        verbose_name = "بازدید یکتا"
        verbose_name_plural = "بازدیدهای یکتا"


class DailyVisitor(models.Model):
    """بازدیدکننده‌ی یکتای سایت در یک روز (هر بازدیدکننده در روز فقط یک بار)."""

    day = models.DateField(db_index=True, verbose_name="روز")
    visitor = models.CharField(max_length=40, verbose_name="بازدیدکننده (هش)")
    is_member = models.BooleanField(default=False, verbose_name="عضو")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["day", "visitor"], name="uniq_daily_visitor")]
        verbose_name = "بازدیدکننده‌ی روزانه"
        verbose_name_plural = "بازدیدکننده‌های روزانه"
