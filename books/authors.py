"""یکتاسازی نام نویسنده و ناشر: کلید مقایسه‌ی نرمال، تطبیق دقیق و تقریبی، و ادغام (بدون ستون تازه).

- کلید مقایسه = همون slug صفحه‌ی نویسنده/ناشر (`author_slug`، `publisher_slug`؛ هر دو index دارن)
  + یکی کردن «آ» با «ا» و حذف فاصله‌ها برای مقایسه‌ی تقریبی.
- فهرست نام‌های موجود از روی همین ستون‌های index‌دار ساخته و ۱۰ دقیقه کش می‌شه؛ تطبیق تقریبی روی همین فهرست حافظه‌ایه.
"""
from collections import Counter
from difflib import SequenceMatcher

from django.core.cache import cache

from common.text import first_author, slugify_fa

FUZZY_THRESHOLD = 0.86
CACHE_SECONDS = 600


def key(name):
    """کلید مقایسه‌ی تقریبی: slug + آ=ا، بدون خط‌تیره."""
    return slugify_fa(first_author(name)).replace("آ", "ا").replace("-", "")


def _build(kind):
    from .models import Book, Edition

    if kind == "author":
        rows = Book.all_objects.filter(deleted_at__isnull=True).exclude(author_slug="").values_list("author_slug", "author")
        names = {}
        for slug, raw in rows.iterator():
            names.setdefault(slug, Counter())[" ".join(first_author(raw).split())] += 1
    else:
        rows = Edition.objects.exclude(publisher_slug="").values_list("publisher_slug", "publisher")
        names = {}
        for slug, raw in rows.iterator():
            names.setdefault(slug, Counter())[" ".join(raw.split())] += 1
    # برای هر slug رایج‌ترین نوشتار + تعداد
    return [(slug, c.most_common(1)[0][0], sum(c.values())) for slug, c in names.items()]


def known(kind="author"):
    """[(slug, نام نمایشی, تعداد)] — کش‌شده."""
    ck = f"hv-names:{kind}"
    data = cache.get(ck)
    if data is None:
        data = _build(kind)
        cache.set(ck, data, CACHE_SECONDS)
    return data


def invalidate(kind=None):
    for k in ([kind] if kind else ["author", "publisher"]):
        cache.delete(f"hv-names:{k}")


def match(name, kind="author", limit=3):
    """('exact', نام موجود) | ('fuzzy', [نام‌های نزدیک]) | (None, None)."""
    if not (name or "").strip():
        return None, None
    slug = slugify_fa(first_author(name)) if kind == "author" else slugify_fa(name)
    k = slug.replace("آ", "ا").replace("-", "")
    rows = known(kind)
    for s, display, _n in rows:
        if s == slug or s.replace("آ", "ا").replace("-", "") == k:
            return "exact", display
    scored = []
    for s, display, n in rows:
        sk = s.replace("آ", "ا").replace("-", "")
        if abs(len(sk) - len(k)) > 3 or not sk or sk[0] != k[:1] and sk[-1:] != k[-1:]:
            continue                                  # پیش‌پالایش ارزون قبل از مقایسه‌ی کامل
        r = SequenceMatcher(None, k, sk).ratio()
        if r >= FUZZY_THRESHOLD:
            scored.append((r, n, display))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return ("fuzzy", [d for _r, _n, d in scored[:limit]]) if scored else (None, None)


def canonicalize(raw):
    """«صادق هدايت، …» ← نوشتار رایج همون نویسنده + بقیه‌ی متن دست‌نخورده."""
    kind, value = match(raw, "author")
    if kind != "exact":
        return raw
    first = first_author(raw)
    return raw.replace(first, value, 1) if first else raw


def duplicate_pairs(kind="author", limit=60):
    """زوج‌های مشکوک به تکراری برای پنل (نزدیک ولی slug متفاوت)."""
    rows = sorted(known(kind), key=lambda t: -t[2])[:2000]
    out = []
    for i, (s1, d1, n1) in enumerate(rows):
        k1 = s1.replace("آ", "ا").replace("-", "")
        for s2, d2, n2 in rows[i + 1:]:
            k2 = s2.replace("آ", "ا").replace("-", "")
            if abs(len(k1) - len(k2)) > 3:
                continue
            if k1 == k2 or SequenceMatcher(None, k1, k2).ratio() >= FUZZY_THRESHOLD:
                keep, drop = ((s1, d1, n1), (s2, d2, n2)) if n1 >= n2 else ((s2, d2, n2), (s1, d1, n1))
                out.append({"keep": keep, "drop": drop})
                if len(out) >= limit:
                    return out
    return out


def merge(kind, drop_slug, keep_name):
    """ادغام: همه‌ی نوشتارهای drop_slug ← keep_name. برمی‌گردونه چند ردیف عوض شد."""
    from .models import Book, Edition, ShelfEntry

    changed = 0
    if kind == "author":
        variants = set()
        for b in Book.all_objects.filter(author_slug=drop_slug):
            first = first_author(b.author)
            variants.add(first)
            b.author = b.author.replace(first, keep_name, 1)
            b.save(update_fields=["author"])
            changed += 1
        if variants:
            changed += ShelfEntry.objects.filter(author__in=variants).update(author=keep_name)
    else:
        for e in Edition.objects.filter(publisher_slug=drop_slug):
            e.publisher = keep_name
            e.save()
            changed += 1
    invalidate(kind)
    return changed


def remember(slug, display, kind="author"):
    """نام تازه رو بدون ساختن دوباره‌ی کل فهرست به کش اضافه می‌کنه."""
    ck = f"hv-names:{kind}"
    data = cache.get(ck)
    if data is not None and slug and all(s != slug for s, _d, _n in data):
        data.append((slug, display, 1))
        cache.set(ck, data, CACHE_SECONDS)
