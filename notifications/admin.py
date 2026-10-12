from django.contrib import admin

from .models import Notification, NotificationPreference, PushSubscription

admin.site.register(Notification)
admin.site.register(NotificationPreference)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "user_agent", "created_at", "last_used_at", "failures")
    readonly_fields = ("endpoint", "p256dh", "auth")
