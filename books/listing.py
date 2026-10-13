"""کمک‌های صفحه‌ی فهرست: نشان‌های کارت (پرتقاضا، هم‌شهری/هم‌استان، مبادله‌دهنده‌ی معتبر) و چیپ‌های فیلتر فعال."""

from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from exchanges.models import Exchange
from trust.models import Vote


def decorate_cards(books, user=None):
    """روی هر کتابِ صفحه‌ی جاری: hot (پرتقاضا)، distance و trusted؛ با دو کوئری جمعی (نه N+1)."""
    books = list(books)
    if not books:
        return books
    since = timezone.now() - timedelta(days=30)
    requested = dict(Exchange.objects.filter(book__in=[b.pk for b in books], created_at__gte=since).values_list("book_id").annotate(n=Count("id")))
    owner_ids = {b.owner_id for b in books}
    votes = {r["target"]: r for r in Vote.objects.filter(target_id__in=owner_ids).values("target").annotate(n=Count("id"), likes=Count("id", filter=Q(like=True)))}
    min_votes = getattr(settings, "CARD_TRUST_MIN_VOTES", 3)
    min_percent = getattr(settings, "CARD_TRUST_PERCENT", 90)
    hot_min = getattr(settings, "CARD_HOT_MIN_REQUESTS", 2)
    my_city = user.city if user is not None and user.is_authenticated and user.city_id else None
    for b in books:
        b.hot = requested.get(b.pk, 0) >= hot_min
        v = votes.get(b.owner_id)
        b.trusted = bool(v and v["n"] >= min_votes and 100 * v["likes"] / v["n"] >= min_percent)
        b.distance = ""
        if my_city and b.city_id:
            if b.city_id == my_city.pk:
                b.distance = "هم‌شهری"
            elif b.city.province_id == my_city.province_id:
                b.distance = "هم‌استان"
    return books


def active_chips(request, cleaned):
    """[(برچسب, نشانی بدون همین فیلتر)]؛ مرتب‌سازی پیش‌فرض و صفحه‌بندی چیپ نمی‌شن."""
    base = request.GET.copy()
    base.pop("page", None)

    def without(*keys):
        params = base.copy()
        for k in keys:
            params.pop(k, None)
        return "?" + urlencode(params, doseq=True) if params else "?"

    chips = []
    if cleaned.get("q"):
        chips.append((f"«{cleaned['q']}»", without("q")))
    if cleaned.get("city"):
        chips.append((cleaned["city"].full_name, without("city", "province")))
    elif cleaned.get("province"):
        chips.append((cleaned["province"].name, without("province")))
    if cleaned.get("category"):
        chips.append((cleaned["category"].name, without("category")))
    if cleaned.get("condition"):
        label = dict(cleaned["_condition_choices"]).get(cleaned["condition"], cleaned["condition"])
        chips.append((label, without("condition")))
    if cleaned.get("sort") and cleaned["sort"] != "new":
        chips.append((dict(cleaned["_sort_choices"])[cleaned["sort"]], without("sort")))
    if cleaned.get("all"):
        chips.append(("با رزروشده‌ها", without("all")))
    return chips, ("?" if chips else "")
