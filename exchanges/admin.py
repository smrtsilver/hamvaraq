from django.contrib import admin, messages

from . import services
from .models import Exchange, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "text", "created_at")
    can_delete = False


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ("book", "owner", "requester", "status", "updated_at")
    list_filter = ("status", ("disputed_at", admin.EmptyFieldListFilter))
    actions = ["force_complete", "force_cancel"]
    search_fields = ("book__title", "owner__username", "requester__username")
    inlines = [MessageInline]


    def _resolve(self, request, queryset, outcome):
        done = 0
        for ex in queryset:
            try:
                services.resolve_dispute(ex.pk, request.user, outcome)
                done += 1
            except services.ExchangeError as e:
                self.message_user(request, f"#{ex.pk}: {e}", messages.WARNING)
        self.message_user(request, f"{done} اختلاف رسیدگی شد.")

    @admin.action(description="اختلاف: تحویل انجام شده ← تکمیل مبادله")
    def force_complete(self, request, queryset):
        self._resolve(request, queryset, "complete")

    @admin.action(description="اختلاف: لغو مبادله و برگشت امتیاز")
    def force_cancel(self, request, queryset):
        self._resolve(request, queryset, "cancel")
