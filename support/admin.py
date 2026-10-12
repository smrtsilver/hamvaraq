from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("__str__", "category", "user", "status", "created_at")
    list_filter = ("status", "category")
    search_fields = ("subject", "message", "user__username")
    readonly_fields = ("user", "page_url", "contact", "created_at", "updated_at")
