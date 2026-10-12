from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from common.views import healthz, home

urlpatterns = [
    path("", home, name="home"),
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("books/", include("books.urls")),
    path("exchanges/", include("exchanges.urls")),
    path("trust/", include("trust.urls")),
    path("notifications/", include("notifications.urls")),
]

handler404 = "common.views.page_not_found"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
