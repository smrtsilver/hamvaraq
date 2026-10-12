from django.conf import settings
from django.db import models
from django.db.models import Q


class Vote(models.Model):
    class Reason(models.TextChoices):
        NO_SHOW = "no_show", "قولش رو زیر پا گذاشت"
        MISMATCH = "mismatch", "کتاب با توضیحات مطابقت نداشت"
        UNRESPONSIVE = "unresponsive", "بی‌پاسخ شد"
        RUDE = "rude", "رفتار نامناسب"
        OTHER = "other", "دلیل دیگر"

    exchange = models.ForeignKey("exchanges.Exchange", on_delete=models.CASCADE, related_name="votes")
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="votes_given")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="votes_received")
    like = models.BooleanField(verbose_name="لایک")
    reason = models.CharField(max_length=14, choices=Reason.choices, blank=True, verbose_name="دلیل")
    comment = models.CharField(max_length=300, blank=True, verbose_name="توضیح")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exchange", "voter"], name="one_vote_per_side")]
        verbose_name = "رأی"
        verbose_name_plural = "رأی‌ها"


class Report(models.Model):
    class Reason(models.TextChoices):
        NO_SHOW = "no_show", "بدقولی"
        SCAM = "scam", "کلاهبرداری یا فروش"
        BAD_BOOK = "bad_book", "کتاب نامناسب"
        ABUSE = "abuse", "محتوای توهین‌آمیز"
        FAKE = "fake", "حساب فیک یا تکراری"
        OTHER = "other", "سایر"

    class Status(models.TextChoices):
        OPEN = "open", "باز"
        REVIEWING = "reviewing", "در بررسی"
        CLOSED = "closed", "بسته‌شده"

    class Decision(models.TextChoices):
        NONE = "", "—"
        REJECT = "reject", "رد گزارش"
        REJECT_WARN_REPORTER = "reject_warn", "رد گزارش و اخطار به گزارش‌دهنده"
        WARN = "warn", "اخطار به متخلف"
        RESTRICT = "restrict", "محدودیت موقت متخلف"
        BAN = "ban", "مسدودسازی متخلف"

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_made", verbose_name="گزارش‌دهنده")
    # هدف دقیقاً یکی از این سه تاست
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="reports_against", verbose_name="کاربر")
    target_book = models.ForeignKey("books.Book", null=True, blank=True, on_delete=models.CASCADE, related_name="reports", verbose_name="کتاب")
    target_message = models.ForeignKey("exchanges.Message", null=True, blank=True, on_delete=models.CASCADE, related_name="reports", verbose_name="پیام")
    reason = models.CharField(max_length=10, choices=Reason.choices, verbose_name="دلیل")
    description = models.TextField(blank=True, verbose_name="توضیح")
    image = models.ImageField(upload_to="reports/%Y/%m/", blank=True, verbose_name="عکس")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True, verbose_name="وضعیت")
    decision = models.CharField(max_length=12, choices=Decision.choices, blank=True, default="", verbose_name="تصمیم")
    decision_note = models.TextField(blank=True, verbose_name="دلیل تصمیم")
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="رسیدگی‌کننده")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(target_user__isnull=False, target_book__isnull=True, target_message__isnull=True)
                    | Q(target_user__isnull=True, target_book__isnull=False, target_message__isnull=True)
                    | Q(target_user__isnull=True, target_book__isnull=True, target_message__isnull=False)
                ),
                name="report_exactly_one_target",
            ),
            # هر کاربر برای هر مورد فقط یک‌بار گزارش می‌ده
            models.UniqueConstraint(fields=["reporter", "target_user"], condition=Q(target_user__isnull=False), name="uniq_report_user"),
            models.UniqueConstraint(fields=["reporter", "target_book"], condition=Q(target_book__isnull=False), name="uniq_report_book"),
            models.UniqueConstraint(fields=["reporter", "target_message"], condition=Q(target_message__isnull=False), name="uniq_report_message"),
        ]
        verbose_name = "گزارش"
        verbose_name_plural = "گزارش‌ها"

    def __str__(self):
        return f"{self.get_reason_display()} — {self.target_label}"

    @property
    def accused(self):
        """کاربری که گزارش علیه‌ی اونه."""
        if self.target_user_id:
            return self.target_user
        if self.target_book_id:
            return self.target_book.owner
        return self.target_message.sender

    @property
    def target_label(self):
        if self.target_user_id:
            return f"کاربر {self.target_user}"
        if self.target_book_id:
            return f"کتاب «{self.target_book}»"
        return f"پیام: {self.target_message.text[:40]}"
