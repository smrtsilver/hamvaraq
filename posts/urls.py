from django.urls import path

from . import views

app_name = "posts"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("new/", views.post_create, name="create"),
    path("mine/", views.my_posts, name="mine"),
    path("preview/", views.preview, name="preview"),
    path("by/<str:username>/", views.author_posts, name="author"),
    path("<str:slug>/", views.post_detail, name="detail"),
    path("<str:slug>/edit/", views.post_edit, name="edit"),
    path("<str:slug>/delete/", views.post_delete, name="delete"),
]
