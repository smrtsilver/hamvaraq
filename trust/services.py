from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from notifications.services import notify

from .models import Report, Vote


def reputation(user):
    """
    اعتبار = درصد لایک وزنی. رأی‌های بین دو نفری که بیش از حد با هم مبادله کردن
    وزن نصف می‌گیرن تا رأی متقابل مشکوک اعتبار نسازه.
    """
    votes = list(Vote.objects.filter(target=user))
    total = len(votes)
    if total == 0:
        return {"newcomer": True, "percent": None, "total": 0, "low": False}
    weighted_like = weighted_total = 0.0
    per_pair = {}
    for v in votes:
        per_pair[v.voter_id] = per_pair.get(v.voter_id, 0) + 1
    for v in votes:
        w = 1.0 if per_pair[v.voter_id] <= settings.MUTUAL_PAIR_FREE_LIMIT else 0.5
        weighted_total += w
        if v.like:
            weighted_like += w
    percent = round(100 * weighted_like / weighted_total)
    low = total >= settings.LOW_REPUTATION_MIN_VOTES and percent < settings.LOW_REPUTATION_PERCENT
    return {"newcomer": False, "percent": percent, "total": total, "low": low}


def can_edit_vote(vote):
    return timezone.now() - vote.created_at <= timedelta(hours=settings.VOTE_EDIT_HOURS)


def apply_decision(report, admin_user):
    """تصمیم ادمین رو روی گزارش و کاربرها اعمال می‌کنه و گزارش‌دهنده رو باخبر می‌کنه."""
    D = Report.Decision
    decision = report.decision
    report.status = Report.Status.CLOSED
    report.closed_at = timezone.now()
    report.handled_by = admin_user
    report.save()

    accused = report.accused          # ممکنه None باشه (اطلاعیه‌ی ثبت‌شده توسط ادمین)
    if accused is None and decision in (D.WARN, D.RESTRICT, D.BAN):
        decision = report.decision = D.REJECT   # کاربری برای اقدام نیست؛ فقط گزارش بسته می‌شه
        report.save(update_fields=["decision"])
    if decision == D.WARN:
        accused.warnings += 1
        notify(accused, f"اخطار از مدیریت: {report.decision_note}", kind="report")
    elif decision == D.RESTRICT:
        _restrict(accused)
        notify(accused, f"حساب تو موقتاً محدود شد (فقط کتاب می‌تونی بدی): {report.decision_note}", kind="report")
    elif decision == D.BAN:
        accused.status = User.Status.BANNED
        accused.is_active = False
    elif decision == D.REJECT_WARN_REPORTER:
        report.reporter.warnings += 1
        report.reporter.save(update_fields=["warnings"])
        notify(report.reporter, f"گزارشت رد شد و اخطار گرفتی: {report.decision_note}", kind="report")

    if decision in (D.WARN, D.RESTRICT, D.BAN):
        accused.save()
        # چند گزارش تأییدشده‌ی بدقولی ← محدودیت خودکار
        if report.reason == Report.Reason.NO_SHOW and accused.status == User.Status.ACTIVE:
            confirmed = Report.objects.filter(
                Q(target_user=accused) | Q(target_book__owner=accused) | Q(target_message__sender=accused) | Q(target_post__author=accused),
                reason=Report.Reason.NO_SHOW,
                decision__in=[D.WARN, D.RESTRICT, D.BAN],
            ).count()
            if confirmed >= settings.NO_SHOW_REPORTS_FOR_RESTRICTION:
                _restrict(accused)
                accused.save()
                notify(accused, "به‌خاطر بدقولی‌های تکراری، حسابت موقتاً محدود شد.", kind="report")

    notify(report.reporter, f"گزارشت درباره‌ی {report.target_label} بررسی و بسته شد.", kind="report")


def _restrict(user):
    user.status = User.Status.RESTRICTED
    user.restricted_until = timezone.now() + timedelta(days=settings.RESTRICTION_DAYS)
