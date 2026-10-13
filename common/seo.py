from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from books.models import Book
from common.models import City, Province


class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return ["home", "books:list", "posts:list", "announcements:list", "cities", "authors", "publishers", "challenges:list", "how_it_works", "rules"]

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


class ProvinceSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.5

    def items(self):
        return Province.objects.filter(cities__books__status=Book.Status.AVAILABLE).distinct()

    def location(self, province):
        return reverse("province", args=[province.pk])


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        from django.utils import timezone

        from posts.models import Post

        return Post.objects.filter(status=Post.Status.PUBLISHED, published_at__lte=timezone.now()).order_by("-published_at")

    def lastmod(self, obj):
        return obj.updated_at


class AnnouncementSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        from announcements.models import Announcement

        return Announcement.objects.filter(status=Announcement.Status.PUBLISHED).order_by("-published_at")

    def lastmod(self, obj):
        return obj.published_at


class AuthorSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return list(Book.objects.filter(status=Book.Status.AVAILABLE).exclude(author_slug="").values_list("author_slug", flat=True).distinct())

    def location(self, slug):
        return reverse("author", args=[slug])


class PublisherSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.4

    def items(self):
        return list(Book.objects.filter(status=Book.Status.AVAILABLE, edition__publisher_slug__gt="").values_list("edition__publisher_slug", flat=True).distinct())

    def location(self, slug):
        return reverse("publisher", args=[slug])


SITEMAPS = {"authors": AuthorSitemap, "publishers": PublisherSitemap, "posts": PostSitemap, "announcements": AnnouncementSitemap, "static": StaticSitemap, "books": BookSitemap, "cities": CitySitemap, "provinces": ProvinceSitemap}

# مسیرهای خصوصی: تو robots.txt بسته‌ان و هدر noindex هم می‌گیرن (RobotsHeaderMiddleware)
PRIVATE_PREFIXES = (
    "/admin/", "/staff/", "/panel/", "/support/mine/", "/analytics/", "/accounts/", "/exchanges/", "/notifications/", "/trust/",
    "/books/new/", "/books/mine/", "/books/bulk/", "/books/wishlist/", "/books/isbn/", "/books/suggest/", "/books/quick/",
    "/posts/new/", "/posts/mine/", "/posts/preview/", "/announcements/new/", "/announcements/mine/",
)


def robots_txt(request):
    lines = ["User-agent: *", *[f"Disallow: {p}" for p in PRIVATE_PREFIXES],
             f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def offline(request):
    return render(request, "offline.html")


def _asset_version():
    """نسخه‌ی کش سرویس‌ورکر: آخرین زمان تغییر فایل‌های استاتیک اصلی (با هر دیپلوی تازه می‌شه)."""
    from pathlib import Path

    from django.conf import settings

    files = [*Path(settings.BASE_DIR, "static", "css").glob("*.css"), *Path(settings.BASE_DIR, "static", "js").glob("*.js"),
             Path(settings.BASE_DIR, "static", "sw.js")]
    newest = max((f.stat().st_mtime for f in files if f.exists()), default=0)
    return format(int(newest), "x")


def service_worker(request):
    """باید از ریشه سرو بشه تا scope کل سایت باشه."""
    from django.contrib.staticfiles import finders

    with open(finders.find("sw.js"), encoding="utf-8") as f:
        body = f.read().replace("__VERSION__", _asset_version())
    resp = HttpResponse(body, content_type="application/javascript")
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
