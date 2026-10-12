from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Badge, User, UserBadge


@admin.register(User)
class HamVaraqUserAdmin(UserAdmin):
    list_display = ("username", "city", "points", "status", "warnings", "is_staff")
    list_filter = ("status", "city", "is_staff", "welcome_granted")
    readonly_fields = UserAdmin.readonly_fields + ("network_id", "welcome_granted")
    @admin.display(description="شناسه‌ی شبکه (هش آی‌پی؛ برابر = هم‌شبکه)")
    def network_id(self, obj):
        return f"ثبت‌نام {obj.signup_ip_hash[:8] or '—'} · آخرین ورود {obj.last_ip_hash[:8] or '—'}"

    fieldsets = UserAdmin.fieldsets + (
        ("هم‌ورق", {"fields": ("city", "points", "status", "restricted_until", "warnings", "welcome_granted", "network_id")}),
    )


admin.site.register(Badge)
admin.site.register(UserBadge)
