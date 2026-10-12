from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from books.models import Book
from common.models import City


class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return ["home", "books:list", "cities", "challenges:list", "how_it_works", "rules"]

    def location(self, name):
        return reverse(name)


class BookSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6
    limit = 2000

    def items(self):
        return Book.objects.filter(status=Book.Status.AVAILABLE).order_by("-created_at")

    def lastmod(self, obj):
        return obj.created_at


class CitySitemap(Sitemap):
    changefreq = "daily"
    priority = 0.5

    def items(self):
        return City.objects.filter(books__status=Book.Status.AVAILABLE).distinct()

    def location(self, city):
        return reverse("city", args=[city.pk])


SITEMAPS = {"static": StaticSitemap, "books": BookSitemap, "cities": CitySitemap}

# مسیرهای خصوصی: تو robots.txt بسته‌ان و هدر noindex هم می‌گیرن (RobotsHeaderMiddleware)
PRIVATE_PREFIXES = (
    "/admin/", "/staff/", "/accounts/", "/exchanges/", "/notifications/", "/trust/",
    "/books/new/", "/books/mine/", "/books/bulk/", "/books/wishlist/", "/books/isbn/",
)


def robots_txt(request):
    lines = ["User-agent: *", *[f"Disallow: {p}" for p in PRIVATE_PREFIXES],
             f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def offline(request):
    return render(request, "offline.html")


def service_worker(request):
    """باید از ریشه سرو بشه تا scope کل سایت باشه."""
    from django.contrib.staticfiles import finders

    with open(finders.find("sw.js"), encoding="utf-8") as f:
        resp = HttpResponse(f.read(), content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache"
    return resp


class RobotsHeaderMiddleware:
    """صفحه‌های خصوصی و شخصی نباید ایندکس بشن."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(PRIVATE_PREFIXES) or request.path.startswith("/accounts/u/"):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
