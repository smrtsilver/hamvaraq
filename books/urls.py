from django.urls import path

from . import views

app_name = "books"

urlpatterns = [
    path("", views.book_list, name="list"),
    path("new/", views.book_create, name="create"),
    path("mine/", views.my_books, name="mine"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/<int:pk>/delete/", views.wishlist_delete, name="wishlist_delete"),
    path("<int:pk>/", views.book_detail, name="detail"),
    path("<int:pk>/edit/", views.book_edit, name="edit"),
    path("<int:pk>/delete/", views.book_delete, name="delete"),
    path("<int:pk>/relist/", views.book_relist, name="relist"),
]
