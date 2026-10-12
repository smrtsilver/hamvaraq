from django.contrib import admin, messages

from . import services
from .models import Post, Tag


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "is_featured", "published_at", "view_count")
    list_filter = ("status", "is_featured")
    search_fields = ("title", "body", "author__username")
    actions = ["approve", "reject_generic"]
    readonly_fields = ("view_count", "created_at", "updated_at")
    raw_id_fields = ("author", "book")

    def save_model(self, request, obj, form, change):
        """تغییر وضعیت از فرم ویرایش هم باید اعلان و انتشار درست داشته باشه."""
        old = Post.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if obj.status == Post.Status.PUBLISHED and old != Post.Status.PUBLISHED:
            services.publish(obj)
        elif obj.status == Post.Status.REJECTED and old != Post.Status.REJECTED:
            services.reject(obj, obj.reject_reason or "با قوانین هم‌خوانی نداشت.")

    @admin.action(description="تأیید و انتشار")
    def approve(self, request, queryset):
        n = 0
        for post in queryset.exclude(status=Post.Status.PUBLISHED):
            services.publish(post)
            n += 1
        self.message_user(request, f"{n} نوشته منتشر شد.")

    @admin.action(description="رد (با دلیل پیش‌فرض)")
    def reject_generic(self, request, queryset):
        for post in queryset.exclude(status=Post.Status.REJECTED):
            services.reject(post, "با قوانین هم‌ورق (تبلیغ، کپی یا محتوای نامناسب) هم‌خوانی نداشت.")
        self.message_user(request, "رد شد؛ برای دلیل دقیق‌تر، نوشته رو باز کن و «دلیل رد» رو بنویس.", messages.INFO)


admin.site.register(Tag)
