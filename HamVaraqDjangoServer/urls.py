from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from common.views import city_detail, city_list, healthz, home

urlpatterns = [
    path("", home, name="home"),
    path("cities/", city_list, name="cities"),
    path("cities/<int:pk>/", city_detail, name="city"),
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("books/", include("books.urls")),
    path("exchanges/", include("exchanges.urls")),
    path("trust/", include("trust.urls")),
    path("challenges/", include("challenges.urls")),
    path("notifications/", include("notifications.urls")),
]

handler404 = "common.views.page_not_found"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
