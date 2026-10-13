from django.contrib import admin

from .models import Club, ClubPost


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "city", "is_online", "is_active", "created_at")
    list_filter = ("is_active", "is_online")
    search_fields = ("name", "current_title")
    raw_id_fields = ("owner", "city")


@admin.register(ClubPost)
class ClubPostAdmin(admin.ModelAdmin):
    list_display = ("club", "user", "created_at")
    raw_id_fields = ("club", "user")
