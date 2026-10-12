from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from announcements.models import Announcement, AnnouncementBookmark
from notifications.services import notify


class Command(BaseCommand):
    help = "برای کسانی که «یادآوری» زدن، قبل از شروع رویداد اعلان می‌فرسته (روزانه تو cron؛ هر نفر فقط یک‌بار)"

    def handle(self, *args, **opts):
        now = timezone.now()
        soon = now + timedelta(hours=settings.EVENT_REMIND_HOURS)
        due = AnnouncementBookmark.objects.filter(
            reminded=False, announcement__status=Announcement.Status.PUBLISHED,
            announcement__starts_at__gt=now, announcement__starts_at__lte=soon,
        ).select_related("user", "announcement")
        n = 0
        for b in due:
            a = b.announcement
            notify(b.user, f"یادآوری: «{a.title}» به‌زودی شروع می‌شه ({a.place_label}).", a.get_absolute_url(), kind="event")
            b.reminded = True
            b.save(update_fields=["reminded"])
            n += 1
        self.stdout.write(f"یادآوری فرستاده‌شده: {n}")
