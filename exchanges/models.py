from django.conf import settings
from django.db import models
from django.db.models import Q


class Exchange(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "درخواست"
        ACCEPTED = "accepted", "تأیید"
        COMPLETED = "completed", "تکمیل"
        CANCELLED = "cancelled", "لغو"
        REJECTED = "rejected", "ردشده"

    ACTIVE = (Status.REQUESTED, Status.ACCEPTED)

    book = models.ForeignKey("books.Book", on_delete=models.PROTECT, related_name="exchanges", verbose_name="کتاب")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_exchanges", verbose_name="درخواست‌دهنده")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_exchanges", verbose_name="صاحب کتاب")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True, verbose_name="وضعیت")
    owner_confirmed = models.BooleanField(default=False, verbose_name="تأیید تحویل توسط صاحب")
    requester_confirmed = models.BooleanField(default=False, verbose_name="تأیید تحویل توسط گیرنده")
    # نقطه‌ی تحویل: یه نفر پیشنهاد می‌ده، طرف مقابل تأیید می‌کنه
    meeting_point = models.ForeignKey("common.MeetingPoint", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="نقطه‌ی تحویل")
    meeting_proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="پیشنهاددهنده‌ی نقطه")
    meeting_agreed = models.BooleanField(default=False, verbose_name="نقطه‌ی تحویل تأیید شد")
    # چرخه‌ی عمر برای یادآوری، انقضا و اختلاف (دستور expire_exchanges)
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تأیید")
    first_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="اولین تأیید تحویل")
    reminder_count = models.PositiveSmallIntegerField(default=0, verbose_name="تعداد یادآوری")
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="لغوکننده")
    cancel_reason = models.CharField(max_length=200, blank=True, verbose_name="دلیل لغو")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان لغو")
    class Delivery(models.TextChoices):
        IN_PERSON = "in_person", "حضوری"
        POSTAL = "postal", "ارسال پستی"

    delivery = models.CharField(max_length=10, choices=Delivery.choices, default=Delivery.IN_PERSON, verbose_name="روش تحویل")
    tracking_code = models.CharField(max_length=40, blank=True, verbose_name="کد رهگیری")
    shipped_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ارسال")
    relist_reminded_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="یادآوری دوباره‌گذاشتن")
    disputed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان اختلاف")
    resolution_note = models.CharField(max_length=300, blank=True, verbose_name="نتیجه‌ی رسیدگی")
    # آخرین باری که هر طرف چت رو دیده (برای شمارش پیام‌های خوانده‌نشده)
    owner_read_at = models.DateTimeField(null=True, blank=True, verbose_name="آخرین دیدن چت (صاحب)")
    requester_read_at = models.DateTimeField(null=True, blank=True, verbose_name="آخرین دیدن چت (گیرنده)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان تکمیل")

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            # یه کتاب هم‌زمان فقط یه مبادله‌ی تأییدشده داره
            models.UniqueConstraint(fields=["book"], condition=Q(status="accepted"), name="one_accepted_per_book"),
            # هر نفر برای یه کتاب فقط یه درخواست فعال داره
            models.UniqueConstraint(
                fields=["book", "requester"], condition=Q(status__in=["requested", "accepted"]),
                name="one_active_request_per_user",
            ),
        ]
        verbose_name = "مبادله"
        verbose_name_plural = "مبادله‌ها"

    def __str__(self):
        return f"{self.book} ← {self.requester}"

    def other_party(self, user):
        return self.requester if user.pk == self.owner_id else self.owner

    def is_party(self, user):
        return user.pk in (self.owner_id, self.requester_id)


class Message(models.Model):
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name="messages", verbose_name="مبادله")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="فرستنده")
    text = models.TextField(max_length=1000, verbose_name="پیام")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        ordering = ["created_at"]
        verbose_name = "پیام"
        verbose_name_plural = "پیام‌ها"

    def __str__(self):
        return self.text[:40]
