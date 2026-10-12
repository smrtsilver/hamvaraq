from django.conf import settings
from django.utils import timezone

from accounts.models import User
from notifications.services import notify

from .models import Announcement


def publish(item, notify_people=True):
    item.status, item.reject_reason = Announcement.Status.PUBLISHED, ""
    if not item.published_at:
        item.published_at = timezone.now()
    if item.pk is None:                      # ثبت‌کننده‌ی staff: اولین ذخیره همین‌جاست
        item.save()
    else:
        item.save(update_fields=["status", "reject_reason", "published_at"])
    if item.submitted_by_id and notify_people and not item.submitted_by.is_staff:
        notify(item.submitted_by, f"اطلاعیه‌ی «{item.title}» منتشر شد.", item.get_absolute_url(), kind="event")
    if notify_people:
        notify_city(item)


def reject(item, reason):
    item.status, item.reject_reason = Announcement.Status.REJECTED, reason[:300]
    item.save(update_fields=["status", "reject_reason"])
    if item.submitted_by_id:
        notify(item.submitted_by, f"اطلاعیه‌ی «{item.title}» منتشر نشد: {item.reject_reason}", "/announcements/mine/", kind="event")


def notify_city(item):
    """رویداد حضوری ← به کاربرهای همون شهر خبر می‌دیم (سقف و بدون ارسال به ثبت‌کننده)."""
    if item.is_online or not item.city_id or item.is_past or item.is_news:
        return 0
    users = User.objects.filter(city_id=item.city_id, is_active=True).exclude(pk=item.submitted_by_id or 0)[: settings.EVENT_CITY_NOTIFY_LIMIT]
    n = 0
    for user in users:
        notify(user, f"اتفاق فرهنگی تازه تو {item.city.name}: {item.title}", item.get_absolute_url(), kind="event")
        n += 1
    return n


def submit(item, user):
    """ثبت‌کننده‌ی staff مستقیم منتشر می‌کنه؛ بقیه می‌رن صف تأیید."""
    item.submitted_by = user
    if user.is_staff:
        publish(item, notify_people=True)
    else:
        item.status = Announcement.Status.PENDING
        item.save()
    return item
