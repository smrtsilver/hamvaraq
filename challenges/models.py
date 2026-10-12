from django.db import models
from django.utils import timezone


class Challenge(models.Model):
    class Kind(models.TextChoices):
        GIVE = "give", "کتاب دادن"
        RECEIVE = "receive", "کتاب گرفتن"
        ANY = "any", "مبادله (دادن یا گرفتن)"

    title = models.CharField(max_length=100, verbose_name="عنوان")
    description = models.CharField(max_length=300, blank=True, verbose_name="توضیح")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.GIVE, verbose_name="نوع")
    target = models.PositiveIntegerField(default=3, verbose_name="تعداد هدف")
    starts_at = models.DateTimeField(verbose_name="شروع")
    ends_at = models.DateTimeField(verbose_name="پایان")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = ["-starts_at"]
        verbose_name = "چالش"
        verbose_name_plural = "چالش‌ها"

    def __str__(self):
        return self.title

    @property
    def is_running(self):
        return self.is_active and self.starts_at <= timezone.now() <= self.ends_at

    def progress(self, user):
        """تعداد مبادله‌های کامل‌شده‌ی کاربر تو بازه‌ی چالش."""
        from django.db.models import Q

        from exchanges.models import Exchange

        qs = Exchange.objects.filter(
            status=Exchange.Status.COMPLETED, completed_at__gte=self.starts_at, completed_at__lte=self.ends_at)
        if self.kind == self.Kind.GIVE:
            qs = qs.filter(owner=user)
        elif self.kind == self.Kind.RECEIVE:
            qs = qs.filter(requester=user)
        else:
            qs = qs.filter(Q(owner=user) | Q(requester=user))
        return qs.count()

    @property
    def badge_code(self):
        return f"challenge-{self.pk}"
