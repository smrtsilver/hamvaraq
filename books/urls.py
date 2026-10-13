from django.urls import path

from . import shelf, views

app_name = "books"

urlpatterns = [
    path("", views.book_list, name="list"),
    path("new/", views.book_create, name="create"),
    path("bulk/", views.book_bulk_create, name="bulk"),
    path("isbn/", views.isbn_view, name="isbn"),
    path("quick/", views.quick_search, name="quick"),
    path("suggest/", views.suggest, name="suggest"),
    path("mine/", views.my_books, name="mine"),
    path("shelf/", shelf.my_shelf, name="shelf"),
    path("shelf/add/", shelf.shelf_add, name="shelf_add"),
    path("shelf/stats/", shelf.shelf_stats, name="shelf_stats"),
    path("shelf/today/", shelf.mark_today, name="mark_today"),
    path("shelf/export/", shelf.shelf_export, name="shelf_export"),
    path("highlights/", shelf.highlights, name="highlights"),
    path("highlights/<int:pk>/delete/", shelf.highlight_delete, name="highlight_delete"),
    path("shelf/<int:pk>/", shelf.shelf_edit, name="shelf_edit"),
    path("shelf/<int:pk>/delete/", shelf.shelf_delete, name="shelf_delete"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/<int:pk>/delete/", views.wishlist_delete, name="wishlist_delete"),
    path("photo/<int:pk>/delete/", views.photo_delete, name="photo_delete"),
    path("photo/<int:pk>/move/", views.photo_move, name="photo_move"),
    path("<int:pk>/", views.book_detail, name="detail"),
    path("<int:pk>/edit/", views.book_edit, name="edit"),
    path("<int:pk>/delete/", views.book_delete, name="delete"),
    path("<int:pk>/review/", views.review_save, name="review"),
    path("<int:pk>/card.png", views.book_card_png, name="card"),
    path("cover-preview/<str:key>.png", views.cover_preview, name="cover_preview"),
    path("<int:pk>/relist/", views.book_relist, name="relist"),
]
