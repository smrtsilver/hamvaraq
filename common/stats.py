"""آمار و تشخیص حساب‌های مشکوک برای داشبورد ادمین و گزارش روزانه."""

from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import User
from books.models import Book
from exchanges.models import Exchange
from trust.models import Report


def _series(qs, field, days, now):
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = qs.filter(**{f"{field}__gte": since}).annotate(d=TruncDate(field)).values("d").annotate(n=Count("id"))
    by_day = {r["d"]: r["n"] for r in rows}
    start = timezone.localtime(since).date()
    return [(start + timedelta(days=i), by_day.get(start + timedelta(days=i), 0)) for i in range(days)]


def suspicious_accounts(now=None):
    """فهرست (کاربر، دلیل). فقط سرنخ برای بررسی دستیه، نه حکم."""
    now = now or timezone.now()
    found = {}

    def flag(user, reason):
        found.setdefault(user.pk, (user, []))[1].append(reason)

    # ۱) جفت‌هایی که بیش از حد با هم مبادله کردن (احتمال جمع‌کردن امتیاز با دو حساب)
    pairs = Counter()
    for owner_id, req_id in Exchange.objects.filter(status=Exchange.Status.COMPLETED).values_list("owner_id", "requester_id"):
        pairs[frozenset((owner_id, req_id))] += 1
    users = User.objects.in_bulk({uid for pair, n in pairs.items() if n > settings.MUTUAL_PAIR_FREE_LIMIT for uid in pair})
    for pair, n in pairs.items():
        if n > settings.MUTUAL_PAIR_FREE_LIMIT:
            a, b = (users[i] for i in pair)
            flag(a, f"{n} مبادله فقط با {b.username}")
            flag(b, f"{n} مبادله فقط با {a.username}")

    # ۲) حساب خیلی تازه با فعالیت زیاد
    week = now - timedelta(days=7)
    for u in User.objects.filter(date_joined__gte=week).annotate(
        done=Count("owned_exchanges", filter=Q(owned_exchanges__status="completed"), distinct=True)
        + Count("requested_exchanges", filter=Q(requested_exchanges__status="completed"), distinct=True)
    ).filter(done__gte=3):
        flag(u, f"حساب کمتر از ۷ روزه با {u.done} مبادله")

    # ۳) چند گزارش علیه یه نفر
    against = Counter()
    for r in Report.objects.exclude(decision=Report.Decision.REJECT).select_related("target_book", "target_message"):
        against[r.accused.pk] += 1
    accused = User.objects.in_bulk([uid for uid, n in against.items() if n >= 2])
    for uid, user in accused.items():
        flag(user, f"{against[uid]} گزارش علیه‌ش")

    # ۴) چند حساب از یه شبکه (احتمال حساب‌های فیک برای امتیاز هدیه)؛ ممکنه خوابگاه یا اینترنت مشترک هم باشه
    groups = (User.objects.exclude(signup_ip_hash="").values("signup_ip_hash").annotate(n=Count("id")).filter(n__gte=3))
    for g in groups:
        members = list(User.objects.filter(signup_ip_hash=g["signup_ip_hash"]))
        for u in members:
            flag(u, f"{g['n']} حساب با ثبت‌نام از یه شبکه")

    # ۵) اخطارهای تکراری
    for u in User.objects.filter(warnings__gte=2):
        flag(u, f"{u.warnings} اخطار")
    return list(found.values())


def collect(now=None):
    now = now or timezone.now()
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    ex = Exchange.objects
    by_status = {row["status"]: row["n"] for row in ex.values("status").annotate(n=Count("id"))}
    stale_requested = ex.filter(
        status=Exchange.Status.REQUESTED, updated_at__lt=now - timedelta(days=settings.STALE_REQUEST_DAYS))
    stale_accepted = ex.filter(
        status=Exchange.Status.ACCEPTED, updated_at__lt=now - timedelta(days=settings.STALE_ACCEPTED_DAYS))
    open_reports = Report.objects.exclude(status=Report.Status.CLOSED)
    oldest = open_reports.order_by("created_at").first()
    return {
        "users": {
            "total": User.objects.count(), "new7": User.objects.filter(date_joined__gte=d7).count(),
            "new30": User.objects.filter(date_joined__gte=d30).count(),
            "restricted": User.objects.filter(status=User.Status.RESTRICTED).count(),
            "banned": User.objects.filter(status=User.Status.BANNED).count(),
        },
        "books": {
            "available": Book.objects.filter(status=Book.Status.AVAILABLE).count(),
            "reserved": Book.objects.filter(status=Book.Status.RESERVED).count(),
            "exchanged": Book.objects.filter(status=Book.Status.EXCHANGED).count(),
            "new7": Book.objects.filter(created_at__gte=d7).count(),
        },
        "exchanges": {
            "by_status": by_status,
            "completed7": ex.filter(status=Exchange.Status.COMPLETED, completed_at__gte=d7).count(),
            "completed30": ex.filter(status=Exchange.Status.COMPLETED, completed_at__gte=d30).count(),
            "stale_requested": stale_requested.count(), "stale_accepted": stale_accepted.count(),
            "disputed": ex.filter(status=Exchange.Status.ACCEPTED, disputed_at__isnull=False).count(),
        },
        "reports": {
            "open": open_reports.filter(status=Report.Status.OPEN).count(),
            "reviewing": open_reports.filter(status=Report.Status.REVIEWING).count(),
            "oldest_days": (now - oldest.created_at).days if oldest else None,
        },
        "daily": {
            "users": _series(User.objects.all(), "date_joined", 14, now),
            "books": _series(Book.objects.all(), "created_at", 14, now),
            "completed": _series(ex.filter(status=Exchange.Status.COMPLETED), "completed_at", 14, now),
        },
        "suspicious": suspicious_accounts(now),
    }
