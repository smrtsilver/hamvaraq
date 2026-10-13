from django.contrib import admin

from .models import Book, BookJourney, BookPhoto, BookNote, Category, Review, ShelfEntry, Wishlist


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


from .models import Edition  # noqa: E402


@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    list_display = ("title", "isbn13", "publisher", "year", "source", "confidence", "verified")
    list_filter = ("source", "verified", "year_calendar")
    search_fields = ("title", "isbn13", "publisher")
    readonly_fields = ("provenance", "created_at", "updated_at")
    actions = ["mark_verified"]

    @admin.action(description="تأیید مدیر (اطمینان حداقل ۹۰)")
    def mark_verified(self, request, queryset):
        for edition in queryset:
            edition.verified = True
            edition.confidence = max(edition.confidence, 90)
            edition.save(update_fields=["verified", "confidence", "updated_at"])


@admin.register(ShelfEntry)
class ShelfEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "user", "reading_status", "rating", "created_at")
    list_filter = ("reading_status",)
    search_fields = ("title", "author", "user__username")
    raw_id_fields = ("user", "book", "edition")
    exclude = ("note",)          # یادداشت خصوصیه؛ حتی مدیر هم تو فرم نمی‌بینه
