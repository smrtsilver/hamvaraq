from django.contrib import admin

from .models import DailyVisitor, ViewLog


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ViewLog)
class ViewLogAdmin(ReadOnly):
    list_display = ("kind", "object_id", "is_member", "created_at")
    list_filter = ("kind", "is_member")


@admin.register(DailyVisitor)
class DailyVisitorAdmin(ReadOnly):
    list_display = ("day", "is_member")
    list_filter = ("is_member",)
