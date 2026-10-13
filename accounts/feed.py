"""فید کتاب‌خوان‌هایی که دنبال می‌کنی: کتاب تموم‌شده/نقد، معرفی منتشرشده، آگهی تازه. فقط خوندنی؛ بدون اعلان."""
from datetime import timedelta

from django.utils import timezone

FEED_DAYS = 60


def build(user, limit=60):
    from books.models import Book, ShelfEntry
    from posts.models import Post

    ids = list(user.following_set.values_list("followee_id", flat=True)[:500])
    if not ids:
        return []
    since = timezone.now() - timedelta(days=FEED_DAYS)
    items = []
    for e in (ShelfEntry.objects.filter(user_id__in=ids, updated_at__gte=since)
              .exclude(reading_status=ShelfEntry.Reading.WANT, review="").select_related("user", "book").order_by("-updated_at")[:limit]):
        kind = "review" if e.review else ("read" if e.reading_status == ShelfEntry.Reading.READ else "reading")
        items.append({"kind": kind, "at": e.updated_at, "user": e.user, "entry": e})
    for p in Post.objects.filter(author_id__in=ids, status=Post.Status.PUBLISHED, published_at__gte=since).select_related("author", "book").order_by("-published_at")[:limit]:
        items.append({"kind": "post", "at": p.published_at, "user": p.author, "post": p})
    for b in Book.objects.filter(owner_id__in=ids, status=Book.Status.AVAILABLE, created_at__gte=since).select_related("owner", "city").order_by("-created_at")[:limit]:
        items.append({"kind": "listing", "at": b.created_at, "user": b.owner, "book": b})
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


def suggested_readers(user, limit=6):
    """کتاب‌خوان‌های فعال با قفسه‌ی مشترک که هنوز دنبالشون نمی‌کنی."""
    from django.db.models import Count

    from books.models import ShelfEntry
    from common.text import work_key

    from .models import User

    mine = {work_key(t, a) for t, a in user.shelf.values_list("title", "author")[:500]}
    skip = set(user.following_set.values_list("followee_id", flat=True)) | {user.pk}
    scores = {}
    if mine:
        for uid, t, a in ShelfEntry.objects.exclude(user_id__in=skip).values_list("user_id", "title", "author")[:5000]:
            if work_key(t, a) in mine:
                scores[uid] = scores.get(uid, 0) + 1
    ranked = [u for u, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:limit]
    if len(ranked) < limit:
        ranked += list(User.objects.filter(is_active=True, deleted_at__isnull=True).exclude(pk__in=skip | set(ranked))
                       .annotate(n=Count("shelf")).filter(n__gt=0).order_by("-n").values_list("pk", flat=True)[:limit - len(ranked)])
    users = {u.pk: u for u in User.objects.filter(pk__in=ranked).annotate(shelf_n=Count("shelf"))}
    out = [users[i] for i in ranked if i in users]
    for u in out:
        u.common = scores.get(u.pk, 0)
    return out
