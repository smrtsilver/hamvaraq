"""آمار برای پنل مدیریت و «آمار من» کاربر. همه‌ی عددها از بازدیدهای یکتا و سخت‌گیرانه‌ی tracking می‌آد."""

from datetime import timedelta
from statistics import median

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import User
from announcements.models import Announcement
from books.models import Book
from exchanges.models import Exchange
from posts.models import Post

from .models import DailyVisitor, ViewLog


def _days(days):
    today = timezone.localdate()
    return [today - timedelta(days=i) for i in range(days - 1, -1, -1)]


def _since(days):
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    return start


def _series(rows, days):
    by_day = dict(rows)
    return [(d, by_day.get(d, 0)) for d in _days(days)]


def _scale(series):
    peak = max([n for _, n in series] + [1])
    return [(d, n, round(100 * n / peak)) for d, n in series]


def _top(kind, model, title_attr, since, limit=8):
    rows = list(ViewLog.objects.filter(kind=kind, created_at__gte=since).values("object_id").annotate(n=Count("id")).order_by("-n")[:limit])
    objs = model.objects.in_bulk([r["object_id"] for r in rows])
    return [(objs[r["object_id"]], r["n"]) for r in rows if r["object_id"] in objs]


def admin_stats(days=30):
    since = _since(days)
    since_day = since.date()
    visitors = DailyVisitor.objects.filter(day__gte=since_day)
    distinct = visitors.values("visitor").distinct()
    daily_all = _series(visitors.values_list("day").annotate(n=Count("id")), days)
    daily_members = _series(visitors.filter(is_member=True).values_list("day").annotate(n=Count("id")), days)
    views = ViewLog.objects.filter(created_at__gte=since)
    views_by_kind = {r["kind"]: r["n"] for r in views.values("kind").annotate(n=Count("id"))}
    views_daily = _series(views.annotate(d=TruncDate("created_at")).values_list("d").annotate(n=Count("id")), days)

    ex = Exchange.objects.filter(created_at__gte=since)
    total = ex.count()
    by_status = {r["status"]: r["n"] for r in ex.values("status").annotate(n=Count("id"))}
    accepted = ex.filter(accepted_at__isnull=False).count()
    completed = ex.filter(status=Exchange.Status.COMPLETED).count()
    waits = [(a - c).total_seconds() / 3600 for c, a in ex.filter(accepted_at__isnull=False).values_list("created_at", "accepted_at")]
    book_views = views_by_kind.get("book", 0)

    def pct(a, b):
        return round(100 * a / b) if b else None

    return {
        "days": days,
        "site": {
            "unique": distinct.count(), "members": distinct.filter(is_member=True).count(),
            "today": DailyVisitor.objects.filter(day=timezone.localdate()).count(),
            "daily": _scale(daily_all), "daily_members": _scale(daily_members),
            "new_users": User.objects.filter(date_joined__gte=since).count(),
        },
        "views": {
            "total": sum(views_by_kind.values()), "by_kind": views_by_kind, "daily": _scale(views_daily),
            "top_books": _top("book", Book, "title", since), "top_posts": _top("post", Post, "title", since), "top_events": _top("event", Announcement, "title", since),
            "all_time": {"book": Book.objects.aggregate(n=Count("id", filter=Q(view_count__gt=0)))["n"], },
        },
        "requests": {
            "total": total, "by_status": by_status, "accepted": accepted, "completed": completed,
            "accept_rate": pct(accepted, total), "completion_rate": pct(completed, accepted),
            "median_hours": round(median(waits), 1) if waits else None,
            "conversion": pct(total, book_views), "daily": _scale(_series(ex.annotate(d=TruncDate("created_at")).values_list("d").annotate(n=Count("id")), days)),
            "top_books": [(r["book__title"], r["book_id"], r["n"]) for r in ex.values("book_id", "book__title").annotate(n=Count("id")).order_by("-n")[:8]],
        },
    }


def user_stats(user):
    books = list(user.books.annotate(req=Count("exchanges", distinct=True),
                                     done=Count("exchanges", filter=Q(exchanges__status=Exchange.Status.COMPLETED), distinct=True)).order_by("-view_count", "-created_at"))
    posts = list(user.posts.filter(status=Post.Status.PUBLISHED).order_by("-view_count"))
    events = list(user.announcements.filter(status=Announcement.Status.PUBLISHED).annotate(saves=Count("bookmarks", distinct=True)).order_by("-view_count"))
    return {
        "books": books, "posts": posts, "events": events,
        "tiles": {
            "book_views": sum(b.view_count for b in books), "requests": sum(b.req for b in books), "done": sum(b.done for b in books),
            "post_views": sum(p.view_count for p in posts), "event_views": sum(e.view_count for e in events),
        },
    }
