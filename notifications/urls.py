from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("read/", views.mark_all_read, name="read_all"),
    path("settings/", views.notification_settings, name="settings"),
    path("push/subscribe/", views.push_subscribe, name="push_subscribe"),
    path("push/unsubscribe/", views.push_unsubscribe, name="push_unsubscribe"),
    path("push/test/", views.push_test, name="push_test"),
]
