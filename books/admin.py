from django.contrib import admin

from .models import Book, BookJourney, BookNote, Category, Review, Wishlist


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "owner", "city", "status", "created_at")
    list_filter = ("status", "condition", "city", "category")
    search_fields = ("title", "author", "isbn", "owner__username")


admin.site.register(Category)
admin.site.register(Wishlist)
admin.site.register(BookNote)
admin.site.register(BookJourney)
admin.site.register(Review)
