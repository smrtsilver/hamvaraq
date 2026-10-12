from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    path("", views.announcement_list, name="list"),
    path("new/", views.announcement_create, name="create"),
    path("mine/", views.my_announcements, name="mine"),
    path("<int:pk>/edit/", views.announcement_edit, name="edit"),
    path("<int:pk>/event.ics", views.announcement_ics, name="ics"),
    path("<int:pk>/bookmark/", views.toggle_bookmark, name="bookmark"),
    path("<int:pk>/<str:slug>/", views.announcement_detail, name="detail"),
    path("<int:pk>/", views.announcement_detail, name="detail_pk"),
]
