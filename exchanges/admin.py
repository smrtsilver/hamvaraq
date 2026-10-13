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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "book":     # کتاب پنهان/حذف‌شده هم باید قابل انتخاب و نمایش باشه
            from books.models import Book

            kwargs["queryset"] = Book.all_objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_inline_instances(self, request, obj=None):
        """چت فقط وقتی برای ادمین دیده می‌شه که اختلاف یا گزارشی روی پیام‌های همین مبادله باشه (حریم خصوصی)."""
        from trust.models import Report

        if obj is None or not (obj.disputed_at or Report.objects.filter(target_message__exchange=obj).exists()):
            return []
        return super().get_inline_instances(request, obj)


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
