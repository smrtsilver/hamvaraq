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

    book = models.ForeignKey("books.Book", on_delete=models.CASCADE, related_name="exchanges", verbose_name="کتاب")
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="requested_exchanges", verbose_name="درخواست‌دهنده")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_exchanges", verbose_name="صاحب کتاب")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True, verbose_name="وضعیت")
    owner_confirmed = models.BooleanField(default=False)
    requester_confirmed = models.BooleanField(default=False)
    # نقطه‌ی تحویل: یه نفر پیشنهاد می‌ده، طرف مقابل تأیید می‌کنه
    meeting_point = models.ForeignKey("common.MeetingPoint", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="نقطه‌ی تحویل")
    meeting_proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    meeting_agreed = models.BooleanField(default=False)
    # آخرین باری که هر طرف چت رو دیده (برای شمارش پیام‌های خوانده‌نشده)
    owner_read_at = models.DateTimeField(null=True, blank=True)
    requester_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

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
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    text = models.TextField(max_length=1000, verbose_name="پیام")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "پیام"
        verbose_name_plural = "پیام‌ها"

    def __str__(self):
        return self.text[:40]
