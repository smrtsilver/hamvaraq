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
    return render(request, "home.html", {"latest": latest, "stats": stats})


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
