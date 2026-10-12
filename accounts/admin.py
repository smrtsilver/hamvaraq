from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Badge, User, UserBadge


@admin.register(User)
class HamVaraqUserAdmin(UserAdmin):
    list_display = ("username", "city", "points", "status", "warnings", "is_staff")
    list_filter = ("status", "city", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("هم‌ورق", {"fields": ("city", "points", "status", "restricted_until", "warnings")}),
    )


admin.site.register(Badge)
admin.site.register(UserBadge)
