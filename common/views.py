from django.conf import settings
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

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
    from datetime import timedelta

    from books.listing import decorate_cards

    since = timezone.now() - timedelta(days=30)
    demand = base.annotate(n_req=Count("exchanges", filter=Q(exchanges__created_at__gte=since))).filter(n_req__gt=0).order_by("-n_req", "-created_at")[:10]
    shelves = []
    new_books = decorate_cards(base[:10], user)
    if local:
        shelves.append({"title": "در شهر " + user.city.name, "sub": "کتاب‌های هم‌شهری‌هات", "books": decorate_cards(local, user), "more": reverse("books:list") + "?city=%d" % user.city_id})
    from books.reading import recommendations

    recs = recommendations(user, 10)
    if recs:
        shelves.append({"title": "پیشنهاد برای تو", "sub": "از روی قفسه‌ات", "books": decorate_cards(recs, user), "more": reverse("books:shelf")})
    shelves.append({"title": "تازه‌ها", "sub": "تازه‌ترین کتاب‌های ثبت‌شده", "books": new_books, "more": reverse("books:list")})
    hot = decorate_cards(demand, user)
    if hot:
        shelves.append({"title": "پرتقاضاها", "sub": "این ماه بیشتر درخواست شدن", "books": hot, "more": reverse("books:list")})
    now = timezone.now()
    challenges = [{"c": c, "done": min(c.progress(user), c.target)} for c in Challenge.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now)[:2]]
    done = Exchange.objects.filter(status=Exchange.Status.COMPLETED)
    return render(request, "home.html", {
        "onboarding": progress(user), "waiting": waiting, "active": active, "shelves": shelves,
        "matches": matches, "challenges": challenges, "events": _upcoming_events(3, user.city), "posts": _latest_posts(3),
        "given": done.filter(owner=user).count(), "received": done.filter(requester=user).count(),
    })


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def healthz(request):
    """سلامت واقعی: اتصال دیتابیس رو هم امتحان می‌کنه (قطع باشه ۵۰۳ می‌ده تا مانیتور و داکر بفهمن)."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return HttpResponse("db down", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")


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


def how_it_works(request):

    from .onboarding import progress

    return render(request, "common/how_it_works.html", {
        "s": settings, "onboarding": progress(request.user) if request.user.is_authenticated else None})


def rules(request):

    return render(request, "common/rules.html", {"s": settings})


STORY_TEMPLATES = [("paper", "کاغذ کهنه"), ("night", "شب کتاب‌خونه"), ("saffron", "زعفرانی"), ("cover", "جلد کتاب")]


def story(request):
    """استوری‌ساز: محتوا (کتاب، نقد، معرفی یا نقل‌قول) سمت سرور پر می‌شه؛ رسم و پیش‌نمایش با canvas در مرورگر.
    پیش‌نمایش همون canvasیه که دانلود می‌شه، پس خروجی دقیقاً همونیه که کاربر می‌بینه."""
    from books.models import Review
    from posts.models import Post

    data = {"mode": "book", "text": "", "title": "", "author": "", "cover": "", "user": "", "stars": 0, "slug": "story"}
    book = None
    pid = request.GET.get("review", "")
    if pid.isdigit():
        r = get_object_or_404(Review.objects.select_related("book", "user"), pk=pid)
        book = r.book
        data.update(mode="review", text=r.text or "", stars=r.stars, user=r.user.username)
    elif request.GET.get("post"):
        p = get_object_or_404(Post.objects.select_related("book", "author"), slug=request.GET["post"], status=Post.Status.PUBLISHED)
        book = p.book
        data.update(mode="review", text=p.excerpt, stars=p.rating or 0, user=p.author.username,
                    title=p.display_book_title, author=p.display_book_author)
    eid = request.GET.get("entry", "")
    if eid.isdigit() and request.user.is_authenticated:
        from books.models import ShelfEntry

        e = get_object_or_404(ShelfEntry.objects.select_related("book"), pk=eid, user=request.user)
        data.update(mode="review", text=e.review, stars=e.rating or 0, user=request.user.username, title=e.title, author=e.author, slug=f"shelf-{e.pk}")
        if e.listing and e.listing.cover:
            data["cover"] = e.listing.cover.url
    bid = request.GET.get("book", "")
    if book is None and bid.isdigit():
        book = get_object_or_404(Book, pk=bid)
    if request.GET.get("mode") == "quote":
        data.update(mode="quote", text=request.GET.get("text", "")[:600])
        for k in ("title", "author"):
            if request.GET.get(k) and not data[k]:
                data[k] = request.GET[k][:150]
    if book is not None:
        data.update(title=book.title, author=book.author, cover=book.cover.url if book.cover else "", slug=f"book-{book.pk}", book=book.pk,
                    city=book.city.name, condition=book.get_condition_display())
        if data["mode"] == "book" and not data["text"]:
            data["text"] = book.description[:220] if book.description else "این کتاب رو رایگان بگیر؛ با یه امتیاز."
    if not data["title"] and data["mode"] != "quote":
        from django.http import Http404
        raise Http404
    return render(request, "common/story.html", {"story": data, "book": book, "templates": STORY_TEMPLATES})
