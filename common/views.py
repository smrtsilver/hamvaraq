from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from accounts.models import User
from books.models import Book, BookJourney
from common.models import City
from exchanges.models import Exchange


def home(request):
    latest = Book.objects.filter(status=Book.Status.AVAILABLE).select_related("city", "category")[:8]
    stats = {
        "books": Book.objects.count(),
        "exchanges": Exchange.objects.filter(status=Exchange.Status.COMPLETED).count(),
    }
    from .onboarding import progress

    onboarding = progress(request.user) if request.user.is_authenticated else None
    return render(request, "home.html", {"latest": latest, "stats": stats, "onboarding": onboarding})


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def healthz(request):
    return HttpResponse("ok")


def city_list(request):
    cities = City.objects.annotate(
        book_count=Count("books", filter=Q(books__status=Book.Status.AVAILABLE), distinct=True),
    ).filter(book_count__gt=0).order_by("-book_count", "name")
    return render(request, "common/city_list.html", {"cities": cities})


def city_detail(request, pk):
    """آمار شهر. «دست‌به‌دست‌شده» یعنی مبادله‌ی کامل‌شده‌ای که مبدأ یا مقصدش این شهره."""
    city = get_object_or_404(City, pk=pk)
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
        "latest": available.select_related("city", "category")[:12],
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
    from django.conf import settings

    from .onboarding import progress

    return render(request, "common/how_it_works.html", {
        "s": settings, "onboarding": progress(request.user) if request.user.is_authenticated else None})


def rules(request):
    from django.conf import settings

    return render(request, "common/rules.html", {"s": settings})
