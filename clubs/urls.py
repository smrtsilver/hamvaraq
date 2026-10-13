from django.urls import path

from . import views

app_name = "clubs"

urlpatterns = [
    path("", views.club_list, name="list"),
    path("new/", views.club_create, name="create"),
    path("post/<int:pk>/delete/", views.post_delete, name="post_delete"),
    path("<str:slug>/", views.club_detail, name="detail"),
    path("<str:slug>/edit/", views.club_edit, name="edit"),
    path("<str:slug>/join/", views.club_join, name="join"),
    path("<str:slug>/propose/", views.propose, name="propose"),
    path("<str:slug>/vote/<int:pk>/", views.vote, name="vote"),
    path("<str:slug>/choose/<int:pk>/", views.choose, name="choose"),
    path("<str:slug>/proposal/<int:pk>/delete/", views.proposal_delete, name="proposal_delete"),
]
