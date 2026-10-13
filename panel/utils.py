from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from common.models import AuditLog

staff_required = staff_member_required(login_url=reverse_lazy("accounts:login"))

NAV = [
    ("index", "نمای کلی", "sparkle"),
    ("reports", "گزارش‌ها", "flag"),
    ("tickets", "مشکلات کاربران", "chat"),
    ("stats", "آمار", "chart"),
    ("exchanges", "مبادله‌ها", "swap"),
    ("users", "کاربران", "user"),
    ("books", "کتاب‌ها", "book"),
    ("posts", "معرفی‌ها", "pen"),
    ("announcements", "اطلاعیه‌ها", "news"),
    ("challenges", "چالش‌ها", "star"),
    ("clubs", "باشگاه‌های کتاب", "chat"),
    ("settings", "تنظیمات سایت", "settings"),
    ("audit", "لاگ مدیریت", "list"),
]


def counts():
    """تعداد موارد منتظر رسیدگی برای نشان کنار منو."""
    from announcements.models import Announcement
    from exchanges.models import Exchange
    from posts.models import Post
    from support.models import Ticket
    from trust.models import Report

    return {
        "reports": Report.objects.exclude(status=Report.Status.CLOSED).count(),
        "tickets": Ticket.objects.filter(status__in=[Ticket.Status.NEW, Ticket.Status.IN_PROGRESS]).count(),
        "exchanges": Exchange.objects.filter(status=Exchange.Status.ACCEPTED, disputed_at__isnull=False).count(),
        "posts": Post.objects.filter(status=Post.Status.PENDING).count(),
        "announcements": Announcement.objects.filter(status=Announcement.Status.PENDING).count(),
    }


def page(request, template, ctx, active):
    ctx = {**ctx, "nav": [(k, label, icon, reverse(f"panel:{k}")) for k, label, icon in NAV], "nav_counts": counts(), "active": active}
    return render(request, template, ctx)


def log(request, action, target="", note=""):
    AuditLog.objects.create(actor=request.user, action=action, target=str(target)[:200], note=note[:300])


def back(request, default):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(default)


def can_manage(actor, target):
    """مدیر عادی روی کاربر عادی؛ فقط سوپرکاربر روی مدیرها؛ هیچ‌کس روی خودش."""
    if target.pk == actor.pk:
        return False
    if (target.is_superuser or target.is_staff) and not actor.is_superuser:
        return False
    return True


def fail(request, text):
    messages.error(request, text)


def search_q(qs, q, fields):
    q = (q or "").strip()
    if not q:
        return qs
    cond = Q()
    for f in fields:
        cond |= Q(**{f"{f}__icontains": q})
    return qs.filter(cond)
