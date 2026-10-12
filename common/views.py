from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from accounts.models import User
from books.models import Book, BookJourney
from common.models import City, Province
from exchanges.models import Exchange


def home(request):
    """مهمان: لندینگ. عضو: «خانه‌ی من» با کارهای در انتظار و پیشنهادها."""
    if request.user.is_authenticated:
        return _member_home(request)
    from .content import FAQ, FEATURES, STEPS

    available = Book.objects.filter(status=Book.Status.AVAILABLE)
    stats = {
        "books": Book.objects.count(),
        "exchanges": Exchange.objects.filter(status=Exchange.Status.COMPLETED).count(),
        "cities": available.values("city").distinct().count(),
        "users": User.objects.filter(is_active=True).count(),
    }
    cities = City.objects.annotate(n=Count("books", filter=Q(books__status=Book.Status.AVAILABLE))).filter(n__gt=0).select_related("province").order_by("-n", "name")[:10]
    return render(request, "landing.html", {
        "latest": available.select_related("city__province", "category")[:8], "stats": stats, "cities": cities,
        "posts": _latest_posts(3), "events": _upcoming_events(3),
        "faq": FAQ, "steps": STEPS, "features": FEATURES, "faq_ld": _faq_ld(FAQ),
    })


def _latest_posts(n):
    from posts.models import Post

    return list(Post.objects.filter(status=Post.Status.PUBLISHED, published_at__lte=timezone.now()).select_related("author", "book").order_by("-is_featured", "-published_at")[:n])


def _upcoming_events(n, city=None):
    from announcements.views import _published, _upcoming
    from django.db.models.functions import Coalesce

    qs = _upcoming(_published())
    if city is not None:
        qs = qs.filter(Q(city=city) | Q(is_online=True))
    return list(qs.order_by("-is_featured", Coalesce("starts_at", "published_at"))[:n])


def _faq_ld(faq):
    import json

    data = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def _member_home(request):
    from challenges.models import Challenge
    from common.text import normalize

    from .onboarding import progress

    user = request.user
    mine = Exchange.objects.filter(Q(owner=user) | Q(requester=user)).select_related("book", "owner", "requester")
    waiting = list(mine.filter(owner=user, status=Exchange.Status.REQUESTED)[:5])
    active = list(mine.filter(status=Exchange.Status.ACCEPTED)[:5])
    base = Book.objects.filter(status=Book.Status.AVAILABLE).exclude(owner=user).select_related("city__province", "category")
    local = list(base.filter(city=user.city)[:8]) if user.city_id else []
    wishes = [normalize(w.text) for w in user.wishes.all()] if settings.WISHLIST_ENABLED else []
    matches = []
    if wishes:
        for b in base[:300]:
            if any(w and (w in b.search_text) for w in wishes):
                matches.append(b)
            if len(matches) == 6:
                break
    now = timezone.now()
    challenges = [{"c": c, "done": min(c.progress(user), c.target)} for c in Challenge.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now)[:2]]
    done = Exchange.objects.filter(status=Exchange.Status.COMPLETED)
    return render(request, "home.html", {
        "onboarding": progress(user), "waiting": waiting, "active": active, "local": local or list(base[:8]), "local_is_city": bool(local),
        "matches": matches, "challenges": challenges, "events": _upcoming_events(3, user.city), "posts": _latest_posts(3),
        "given": done.filter(owner=user).count(), "received": done.filter(requester=user).count(),
    })


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def healthz(request):
    return HttpResponse("ok")


def city_list(request):
    """استان‌ها با شهرهایی که کتاب موجود دارن (گروه‌بندی‌شده)."""
    from django.db.models import Prefetch

    live = City.objects.annotate(
        book_count=Count("books", filter=Q(books__status=Book.Status.AVAILABLE), distinct=True)).filter(book_count__gt=0)
    provinces = Province.objects.prefetch_related(Prefetch("cities", queryset=live.order_by("-book_count", "name"), to_attr="live_cities"))
    groups = []
    for province in provinces:
        if province.live_cities:
            groups.append({"province": province, "cities": province.live_cities,
                           "total": sum(c.book_count for c in province.live_cities)})
    groups.sort(key=lambda g: (-g["total"], g["province"].name))
    return render(request, "common/city_list.html", {"groups": groups})


def province_detail(request, pk):
    province = get_object_or_404(Province, pk=pk)
    available = Book.objects.filter(city__province=province, status=Book.Status.AVAILABLE)
    cities = City.objects.filter(province=province).annotate(
        book_count=Count("books", filter=Q(books__status=Book.Status.AVAILABLE), distinct=True)).filter(book_count__gt=0).order_by("-book_count", "name")
    exchanged = BookJourney.objects.filter(Q(from_city__province=province) | Q(to_city__province=province)).count()
    return render(request, "common/province_detail.html", {
        "province": province, "cities": cities, "latest": available.select_related("city__province", "category")[:12],
        "stats": {"available": available.count(), "exchanged": exchanged,
                  "users": User.objects.filter(city__province=province, is_active=True).count()},
    })


def city_detail(request, pk):
    """آمار شهر. «دست‌به‌دست‌شده» یعنی مبادله‌ی کامل‌شده‌ای که مبدأ یا مقصدش این شهره."""
    city = get_object_or_404(City.objects.select_related("province"), pk=pk)
    available = Book.objects.filter(city=city, status=Book.Status.AVAILABLE)
    exchanged = BookJourney.objects.filter(Q(from_city=city) | Q(to_city=city)).count()
    stats = {
        "available": available.count(),
        "exchanged": exchanged,
        "users": User.objects.filter(city=city, is_active=True).count(),
    }
    top_categories = available.exclude(category=None).values("category__name").annotate(n=Count("id")).order_by("-n")[:5]
    return render(request, "common/city_detail.html", {
        "city": city, "stats": stats, "top_categories": top_categories,
        "latest": available.select_related("city__province", "category")[:12],
    })


@staff_member_required
def staff_dashboard(request):
    from .stats import collect

    data = collect()
    peak = max([n for series in data["daily"].values() for _, n in series] + [1])
    # هر سری رو برای رسم میله‌ای با درصد ارتفاع آماده می‌کنیم
    data["daily"] = {k: [(d, n, round(100 * n / peak)) for d, n in v] for k, v in data["daily"].items()}
    return render(request, "common/staff_dashboard.html", {"d": data})


def how_it_works(request):

    from .onboarding import progress

    return render(request, "common/how_it_works.html", {
        "s": settings, "onboarding": progress(request.user) if request.user.is_authenticated else None})


def rules(request):

    return render(request, "common/rules.html", {"s": settings})
