from django.contrib import admin

from .models import Book, BookJourney, BookPhoto, BookNote, Category, Review, Wishlist


class BookPhotoInline(admin.TabularInline):
    model = BookPhoto
    extra = 0


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "owner", "city", "status", "deleted_at", "created_at")
    list_filter = ("status", "condition", "city", "category")
    search_fields = ("title", "author", "isbn", "owner__username")
    inlines = [BookPhotoInline]
    readonly_fields = ("deleted_at",)

    def get_queryset(self, request):
        return Book.all_objects.select_related("owner", "city")


admin.site.register(Category)
admin.site.register(Wishlist)
admin.site.register(BookNote)
admin.site.register(BookJourney)
admin.site.register(Review)
