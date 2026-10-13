"""منطق کتابخونه‌ی شخصی: سال شمسی، هدف و آمار خواندن، تطبیق «می‌خواهم بخوانم» با آگهی‌ها و پیشنهاد کتاب."""
from collections import Counter

import jdatetime
from django.db.models import Avg, Count
from django.utils import timezone

from common.text import work_key

from .models import Book, ReadingGoal, ShelfEntry


def current_jyear():
    return jdatetime.date.fromgregorian(date=timezone.localdate()).year


def jyear_range(year):
    """[شروع، پایان) سال شمسی به میلادی."""
    return jdatetime.date(year, 1, 1).togregorian(), jdatetime.date(year + 1, 1, 1).togregorian()


def read_in_year(user, year):
    start, end = jyear_range(year)
    return user.shelf.filter(reading_status=ShelfEntry.Reading.READ, finished_at__gte=start, finished_at__lt=end)


def goal_progress(user, year=None):
    """{'year', 'target', 'done', 'percent', 'ahead'} یا None اگه هدفی نذاشته."""
    year = year or current_jyear()
    goal = ReadingGoal.objects.filter(user=user, year=year).first()
    if not goal:
        return None
    done = read_in_year(user, year).count()
    start, end = jyear_range(year)
    today = timezone.localdate()
    elapsed = max(0.0, min(1.0, (today - start).days / max(1, (end - start).days))) if year == current_jyear() else (1.0 if today >= end else 0.0)
    expected = goal.target * elapsed
    return {"year": year, "target": goal.target, "done": done, "percent": min(100, round(100 * done / goal.target)),
            "ahead": done - round(expected), "goal": goal}


def reading_stats(user, year):
    read = read_in_year(user, year)
    months = [0] * 12
    for d in read.values_list("finished_at", flat=True):
        months[jdatetime.date.fromgregorian(date=d).month - 1] += 1
    top = max(months) or 1
    authors = Counter(read.values_list("author", flat=True)).most_common(5)
    agg = read.aggregate(avg=Avg("rating"), n=Count("id"))
    pages = sum(p for p in read.values_list("edition__pages", flat=True) if p)
    by_status = dict(user.shelf.values_list("reading_status").annotate(n=Count("id")))
    return {"months": [(m, n, round(100 * n / top)) for m, n in zip(jdatetime.date.j_months_fa, months)],
            "authors": authors, "count": agg["n"], "avg": agg["avg"], "pages": pages,
            "reviews": read.exclude(review="").count(), "by_status": by_status}


def wanted_matches(user, entries):
    """برای ردیف‌های «می‌خواهم بخوانم»: آگهی‌های موجودِ همون کتاب (از بقیه). {entry_id: [Book…]}"""
    keys = {}
    for e in entries:
        if e.reading_status == ShelfEntry.Reading.WANT and not e.listing:
            keys.setdefault(work_key(e.title, e.author), []).append(e.pk)
    if not keys:
        return {}
    out = {}
    books = (Book.objects.filter(work_key__in=keys, status=Book.Status.AVAILABLE).exclude(owner=user)
             .select_related("city").order_by("-created_at")[:200])
    for b in books:
        for eid in keys.get(b.work_key, []):
            out.setdefault(eid, []).append(b)
    return out


def recommendations(user, limit=12):
    """پیشنهاد آگهی‌های موجود از روی قفسه: نویسنده‌های محبوب کاربر + کتاب‌هایی که هم‌قفسه‌ای‌هاش دارن."""
    mine = list(user.shelf.values_list("title", "author", "rating", "reading_status"))
    if not mine:
        return []
    have = {work_key(t, a) for t, a, _r, _s in mine}
    fav = Counter()
    for _t, a, r, s in mine:
        fav[a] += (r or 3) if s == ShelfEntry.Reading.READ else 2
    authors = [a for a, _ in fav.most_common(8)]
    base = Book.objects.filter(status=Book.Status.AVAILABLE).exclude(owner=user).exclude(work_key__in=have).select_related("city")
    picks, seen = [], set()
    for b in base.filter(author__in=authors).order_by("-created_at")[:limit * 2]:
        if b.work_key not in seen:
            seen.add(b.work_key)
            b.why = f"چون {b.author} رو دوست داری"
            picks.append(b)
    if len(picks) < limit:
        # هم‌قفسه‌ای‌ها: کسایی که حداقل یه کتاب مشترک دارن؛ کتاب‌های پرتکرار قفسه‌شون
        peers = (ShelfEntry.objects.filter(title__in=[t for t, *_ in mine]).exclude(user=user)
                 .values_list("user_id", flat=True).distinct()[:200])
        co = Counter(work_key(t, a) for t, a in ShelfEntry.objects.filter(user_id__in=list(peers)).values_list("title", "author")[:3000])
        wanted = [k for k, _ in co.most_common(60) if k not in have and k not in seen]
        for b in base.filter(work_key__in=wanted).order_by("-created_at")[:limit]:
            if b.work_key not in seen and len(picks) < limit:
                seen.add(b.work_key)
                b.why = "کتاب‌خوان‌های هم‌سلیقه‌ات دارنش"
                picks.append(b)
    return picks[:limit]


def streak(user, days=28):
    """سری خواندن: {'current', 'best', 'today', 'grid': [(date, bool)…]} — فقط از روی «امروز خوندم»‌های خود کاربر."""
    from datetime import timedelta

    from .models import ReadingDay

    today = timezone.localdate()
    marked = set(ReadingDay.objects.filter(user=user, day__gte=today - timedelta(days=400)).values_list("day", flat=True))
    cur, d = 0, today if today in marked else today - timedelta(days=1)   # اگه امروز هنوز نزده، سری دیروز هنوز زنده‌ست
    while d in marked:
        cur += 1
        d -= timedelta(days=1)
    best, run = 0, 0
    for i in range(400, -1, -1):
        if today - timedelta(days=i) in marked:
            run += 1
            best = max(best, run)
        else:
            run = 0
    grid = [(today - timedelta(days=i), (today - timedelta(days=i)) in marked) for i in range(days - 1, -1, -1)]
    return {"current": cur, "best": best, "today": today in marked, "grid": grid}
