"""ارسال Web Push (اعلان بیرون از سایت). بدون کلیدهای VAPID هیچ کاری نمی‌کنه و بقیه‌ی سایت دست‌نخورده می‌مونه."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import connections
from django.utils import timezone

from .models import Notification, NotificationPreference, PushSubscription

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webpush")
MAX_FAILURES = 5
TITLES = {
    "exchange": "مبادله‌ی کتاب", "chat": "پیام تازه", "wishlist": "کتاب دلخواهت ثبت شد",
    "badge": "نشان تازه", "report": "گزارش", "event": "اطلاعیه‌ی فرهنگی", "system": "هم‌ورق",
}


def configured():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def payload_for(note):
    return {
        "title": TITLES.get(note.kind, "هم‌ورق"), "body": note.text, "url": note.url or "/",
        "tag": f"{note.kind}-{note.url or note.pk}", "icon": "/static/brand/icon-192.png", "badge": "/static/brand/favicon-48.png",
    }


def send_payload(user_id, payload):
    """به همه‌ی دستگاه‌های کاربر می‌فرسته؛ تعداد ارسال موفق رو برمی‌گردونه. اشتراک‌های مرده پاک می‌شن."""
    from pywebpush import WebPushException, webpush

    sent = 0
    for sub in PushSubscription.objects.filter(user_id=user_id):
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=60 * 60 * 24, timeout=8,
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):          # اشتراک منقضی/لغوشده
                sub.delete()
                continue
            sub.failures += 1
            if sub.failures >= MAX_FAILURES:
                sub.delete()
            else:
                sub.save(update_fields=["failures"])
            log.warning("webpush failed (%s) for subscription %s", status, sub.pk)
        except Exception:  # noqa: BLE001 — خطای شبکه نباید سایت رو از کار بندازه
            log.exception("webpush error")
        else:
            sub.last_used_at, sub.failures = timezone.now(), 0
            sub.save(update_fields=["last_used_at", "failures"])
            sent += 1
    return sent


def _run(user_id, payload):
    try:
        send_payload(user_id, payload)
    finally:
        connections.close_all()  # اتصال دیتابیس ترد


def dispatch(note: Notification):
    if not configured() or not NotificationPreference.allows(note.user, note.kind):
        return
    if not PushSubscription.objects.filter(user_id=note.user_id).exists():
        return
    payload = payload_for(note)
    if settings.PUSH_SYNC:
        send_payload(note.user_id, payload)
    else:
        _executor.submit(_run, note.user_id, payload)
