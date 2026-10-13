from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import RedirectView

from common.seo import SITEMAPS, offline, robots_txt, service_worker
from books import facets
from common.csp import report as csp_report
from common.views import city_detail, city_list, healthz, home, how_it_works, province_detail, rules, story

urlpatterns = [
    path("", home, name="home"),
    path("how-it-works/", how_it_works, name="how_it_works"),
    path("rules/", rules, name="rules"),
    path("story/", story, name="story"),
    path("authors/", facets.author_list, name="authors"),
    path("authors/<str:slug>/", facets.author_detail, name="author"),
    path("publishers/", facets.publisher_list, name="publishers"),
    path("publishers/<str:slug>/", facets.publisher_detail, name="publisher"),
    path("cities/", city_list, name="cities"),
    path("cities/<int:pk>/", city_detail, name="city"),
    path("provinces/<int:pk>/", province_detail, name="province"),
    path("staff/", RedirectView.as_view(pattern_name="panel:index"), name="staff_dashboard"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots"),
    path("sw.js", service_worker, name="sw"),
    path("offline/", offline, name="offline"),
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "favicon.svg", permanent=True)),
    path("healthz/", healthz, name="healthz"),
    path("clubs/", include("clubs.urls")),
    path("csp-report/", csp_report, name="csp_report"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("books/", include("books.urls")),
    path("exchanges/", include("exchanges.urls")),
    path("trust/", include("trust.urls")),
    path("challenges/", include("challenges.urls")),
    path("posts/", include("posts.urls")),
    path("announcements/", include("announcements.urls")),
    path("notifications/", include("notifications.urls")),
    path("support/", include("support.urls")),
    path("analytics/", include("analytics.urls")),
    path("panel/", include("panel.urls")),
]

handler404 = "common.views.page_not_found"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
