from django.contrib import admin, messages
from django.db.models import Q

from .models import Report, Vote
from .services import apply_decision


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reporter", "reason", "status", "decision", "created_at")
    list_filter = ("status", "reason", "decision")
    search_fields = ("reporter__username", "description")
    readonly_fields = (
        "reporter", "target_user", "target_book", "target_message", "reason", "description", "image",
        "created_at", "closed_at", "handled_by", "context",
    )
    fields = readonly_fields + ("status", "decision", "decision_note")

    @admin.display(description="زمینه (تاریخچه‌ی مبادله و چت مربوط)")
    def context(self, obj):
        from django.utils.html import format_html_join

        from exchanges.models import Exchange

        user = obj.accused
        lines = []
        if obj.target_message_id:
            ex = obj.target_message.exchange
            lines += [(f"{m.sender}: {m.text}",) for m in ex.messages.all()]
        else:
            # چت فقط وقتی دیده می‌شه که گزارش مستقیماً به پیام مربوط باشه
            for ex in Exchange.objects.filter(Q(owner=user) | Q(requester=user))[:20]:
                lines.append((f"مبادله #{ex.pk} — {ex.status}",))
        return format_html_join("", "<div>{}</div>", lines) or "—"

    def save_model(self, request, obj, form, change):
        if obj.decision and obj.status != Report.Status.CLOSED:
            if not obj.decision_note.strip():
                messages.error(request, "برای ثبت تصمیم باید دلیلش رو بنویسی.")
                obj.decision = ""
                super().save_model(request, obj, form, change)
                return
            apply_decision(obj, request.user)
            return
        super().save_model(request, obj, form, change)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("exchange", "voter", "target", "like", "reason", "created_at")
    list_filter = ("like", "reason")
