from django.contrib import admin

from .models import Exchange, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "text", "created_at")
    can_delete = False


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ("book", "owner", "requester", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("book__title", "owner__username", "requester__username")
    inlines = [MessageInline]
