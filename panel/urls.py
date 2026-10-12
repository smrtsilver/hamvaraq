from django.urls import path

from . import views

app_name = "panel"
urlpatterns = [
    path("", views.index, name="index"),
    path("stats/", views.stats, name="stats"),
    path("reports/", views.reports, name="reports"),
    path("reports/<int:pk>/", views.report_detail, name="report"),
    path("reports/<int:pk>/reviewing/", views.report_reviewing, name="report_reviewing"),
    path("tickets/", views.tickets, name="tickets"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket"),
    path("exchanges/", views.exchanges, name="exchanges"),
    path("exchanges/<int:pk>/resolve/", views.exchange_resolve, name="exchange_resolve"),
    path("users/", views.users, name="users"),
    path("users/<int:pk>/", views.user_detail, name="user"),
    path("users/<int:pk>/action/", views.user_action, name="user_action"),
    path("books/", views.books, name="books"),
    path("books/<int:pk>/delete/", views.book_delete, name="book_delete"),
    path("posts/", views.posts, name="posts"),
    path("posts/<int:pk>/action/", views.post_action, name="post_action"),
    path("announcements/", views.announcements, name="announcements"),
    path("announcements/<int:pk>/action/", views.announcement_action, name="announcement_action"),
    path("challenges/", views.challenges, name="challenges"),
    path("challenges/new/", views.challenge_form, name="challenge_new"),
    path("challenges/<int:pk>/edit/", views.challenge_form, name="challenge_edit"),
    path("challenges/<int:pk>/action/", views.challenge_action, name="challenge_action"),
    path("settings/", views.settings_view, name="settings"),
    path("audit/", views.audit, name="audit"),
]
