from django.contrib import admin, messages

from . import services
from .models import Announcement, AnnouncementBookmark


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "starts_at", "city", "submitted_by", "is_featured")
    list_filter = ("status", "kind", "is_online", "is_featured")
    search_fields = ("title", "summary", "venue", "organizer")
    actions = ["approve", "reject_generic"]
    readonly_fields = ("view_count", "created_at")
    raw_id_fields = ("submitted_by", "city")

    def save_model(self, request, obj, form, change):
        old = Announcement.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if obj.status == Announcement.Status.PUBLISHED and old != Announcement.Status.PUBLISHED:
            services.publish(obj)
        elif obj.status == Announcement.Status.REJECTED and old != Announcement.Status.REJECTED:
            services.reject(obj, obj.reject_reason or "با قوانین هم‌ورق هم‌خوانی نداشت.")

    @admin.action(description="تأیید و انتشار")
    def approve(self, request, queryset):
        n = 0
        for item in queryset.exclude(status=Announcement.Status.PUBLISHED):
            services.publish(item)
            n += 1
        self.message_user(request, f"{n} اطلاعیه منتشر شد.")

    @admin.action(description="رد (با دلیل پیش‌فرض)")
    def reject_generic(self, request, queryset):
        for item in queryset.exclude(status=Announcement.Status.REJECTED):
            services.reject(item, "با قوانین هم‌ورق (تبلیغ، اطلاعات ناقص یا نامرتبط) هم‌خوانی نداشت.")
        self.message_user(request, "رد شد؛ برای دلیل دقیق‌تر اطلاعیه رو باز کن و «دلیل رد» رو بنویس.", messages.INFO)


admin.site.register(AnnouncementBookmark)
