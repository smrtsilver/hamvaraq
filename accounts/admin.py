from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Badge, User, UserBadge


@admin.register(User)
class HamVaraqUserAdmin(UserAdmin):
    list_display = ("username", "city", "points", "status", "warnings", "is_staff")
    list_filter = ("status", "city", "is_staff", "welcome_granted")
    readonly_fields = UserAdmin.readonly_fields + ("network_id", "welcome_granted", "deleted_at")
    actions = ["anonymize"]

    @admin.action(description="ناشناس‌سازی حساب (به‌جای حذف؛ تاریخچه می‌مونه)")
    def anonymize(self, request, queryset):
        from .services import AccountError, anonymize_user

        for user in queryset:
            try:
                anonymize_user(user)
                self.message_user(request, f"{user.pk} ناشناس شد.")
            except AccountError as e:
                self.message_user(request, f"{user.username}: {e}", level="error")

    @admin.display(description="شناسه‌ی شبکه (هش آی‌پی؛ برابر = هم‌شبکه)")
    def network_id(self, obj):
        return f"ثبت‌نام {obj.signup_ip_hash[:8] or '—'} · آخرین ورود {obj.last_ip_hash[:8] or '—'}"

    fieldsets = UserAdmin.fieldsets + (
        ("هم‌ورق", {"fields": ("city", "points", "status", "restricted_until", "warnings", "welcome_granted", "network_id", "deleted_at")}),
    )


admin.site.register(Badge)
admin.site.register(UserBadge)
