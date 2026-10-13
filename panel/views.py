from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from announcements import services as ann_services
from announcements.models import Announcement
from books.models import Book
from challenges.models import Challenge
from common import points
from common.models import AuditLog, SiteSetting
from common.stats import collect
from exchanges import services as ex_services
from exchanges.models import Exchange
from notifications.services import notify
from posts import services as post_services
from posts.models import Post
from support.models import Ticket
from trust.models import Report
from trust.services import _restrict, apply_decision, reputation

from .forms import ChallengeForm, DecisionForm, NoteForm, PointsForm, SiteSettingForm, TicketReplyForm
from .utils import back, can_manage, fail, log, page, search_q, staff_required

PER_PAGE = 25
REPORT_TABS = [("open", "باز"), ("reviewing", "در بررسی"), ("closed", "بسته‌شده")]
TICKET_TABS = [("open", "باز"), ("new", "جدید"), ("in_progress", "در حال بررسی"), ("resolved", "حل‌شده"), ("closed", "بسته‌شده")]
USER_TABS = [("", "همه"), ("new", "تازه (۷ روز)"), ("warned", "اخطارگرفته"), ("restricted", "محدود"), ("banned", "مسدود"), ("staff", "مدیرها")]
USER_ACTIONS = [("warn", "اخطار", "btn-secondary"), ("restrict", "محدودیت موقت", "btn-secondary"), ("ban", "مسدودسازی", "btn-danger"), ("lift", "رفع محدودیت/مسدودی", "btn-ghost")]


def _paginate(request, qs):
    return Paginator(qs, PER_PAGE).get_page(request.GET.get("page"))


def _qs(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


# ---------------------------------------------------------------- نمای کلی
@staff_required
def index(request):
    data = collect()
    peak = max([n for series in data["daily"].values() for _, n in series] + [1])
    data["daily"] = {k: [(d, n, round(100 * n / peak)) for d, n in v] for k, v in data["daily"].items()}
    return page(request, "panel/index.html", {"d": data, "logs": AuditLog.objects.select_related("actor")[:8], "kpi": community_kpis()}, "index")


def community_kpis():
    """شاخص‌های کتاب‌خوانی (قفسه، هدف، باشگاه، دنبال‌کردن)؛ با کش ۵ دقیقه‌ای تا داشبورد سبک بمونه."""
    from django.core.cache import cache

    def build():
        from accounts.models import Follow
        from books.models import Highlight, ReadingGoal, ShelfEntry
        from clubs.models import Club

        week = timezone.now() - timedelta(days=7)
        return {
            "shelf": ShelfEntry.objects.count(), "shelf7": ShelfEntry.objects.filter(created_at__gte=week).count(),
            "read7": ShelfEntry.objects.filter(reading_status="read", finished_at__gte=week.date()).count(),
            "goals": ReadingGoal.objects.count(), "clubs": Club.objects.filter(is_active=True).count(),
            "follows": Follow.objects.count(), "highlights": Highlight.objects.count(),
        }
    return cache.get_or_set("panel:kpi", build, 300)


# ---------------------------------------------------------------- آمار
@staff_required
def stats(request):
    from analytics.services import admin_stats

    days = int(request.GET.get("days", 30)) if request.GET.get("days") in ("7", "30", "90") else 30
    return page(request, "panel/stats.html", {"s": admin_stats(days), "days": days, "ranges": (7, 30, 90), "status_labels": Exchange.Status.choices}, "stats")


# ---------------------------------------------------------------- گزارش‌ها
@staff_required
def reports(request):
    status = request.GET.get("status", "open")
    qs = Report.objects.select_related("reporter", "target_user", "target_book", "target_post", "target_announcement", "target_message")
    if status == "open":
        qs = qs.exclude(status=Report.Status.CLOSED)
    elif status in Report.Status.values:
        qs = qs.filter(status=status)
    reason = request.GET.get("reason", "")
    if reason in Report.Reason.values:
        qs = qs.filter(reason=reason)
    return page(request, "panel/reports.html", {"page": _paginate(request, qs), "status": status, "reason": reason,
                                                 "qs": _qs(request), "reasons": Report.Reason.choices, "report_tabs": REPORT_TABS}, "reports")


@staff_required
def report_detail(request, pk):
    report = get_object_or_404(Report.objects.select_related("reporter", "handled_by"), pk=pk)
    form = DecisionForm(request.POST or None)
    if request.method == "POST" and report.status != Report.Status.CLOSED and form.is_valid():
        report.decision, report.decision_note = form.cleaned_data["decision"], form.cleaned_data["decision_note"].strip()
        apply_decision(report, request.user)
        log(request, f"تصمیم گزارش: {report.get_decision_display()}", f"گزارش #{report.pk}", report.decision_note)
        messages.success(request, "تصمیم اعمال شد و گزارش‌دهنده باخبر شد.")
        return redirect("panel:reports")
    accused = report.accused
    history = []
    if accused:
        history = Exchange.objects.filter(Q(owner=accused) | Q(requester=accused)).select_related("book").order_by("-created_at")[:10]
    chat = report.target_message.exchange.messages.select_related("sender")[:30] if report.target_message_id else []
    return page(request, "panel/report_detail.html", {"r": report, "form": form, "accused": accused, "history": history, "chat": chat}, "reports")


@staff_required
@require_POST
def report_reviewing(request, pk):
    Report.objects.filter(pk=pk, status=Report.Status.OPEN).update(status=Report.Status.REVIEWING)
    log(request, "گزارش در بررسی", f"گزارش #{pk}")
    return back(request, "panel:reports")


# ---------------------------------------------------------------- مشکلات کاربران
@staff_required
def tickets(request):
    status = request.GET.get("status", "open")
    qs = Ticket.objects.select_related("user")
    if status == "open":
        qs = qs.filter(status__in=[Ticket.Status.NEW, Ticket.Status.IN_PROGRESS])
    elif status in Ticket.Status.values:
        qs = qs.filter(status=status)
    cat = request.GET.get("category", "")
    if cat in Ticket.Category.values:
        qs = qs.filter(category=cat)
    qs = search_q(qs, request.GET.get("q"), ["subject", "message", "user__username"])
    return page(request, "panel/tickets.html", {"page": _paginate(request, qs), "status": status, "category": cat, "q": request.GET.get("q", ""),
                                                 "qs": _qs(request), "categories": Ticket.Category.choices, "ticket_tabs": TICKET_TABS}, "tickets")


@staff_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("user"), pk=pk)
    form = TicketReplyForm(request.POST or None, instance=ticket)
    if request.method == "POST" and form.is_valid():
        changed = form.has_changed()
        t = form.save(commit=False)
        t.handled_by = request.user
        t.save()
        if changed and t.user_id:
            text = "مدیریت به گزارش «%s» پاسخ داد." % t.subject if "reply" in form.changed_data and t.reply else f"وضعیت گزارش «{t.subject}»: {t.get_status_display()}"
            notify(t.user, text, t.get_absolute_url(), kind="report")
        log(request, f"گزارش مشکل: {t.get_status_display()}", f"#{t.pk} {t.subject}")
        messages.success(request, "ذخیره شد.")
        return redirect("panel:tickets")
    return page(request, "panel/ticket_detail.html", {"t": ticket, "form": form}, "tickets")


# ---------------------------------------------------------------- مبادله‌ها
@staff_required
def exchanges(request):
    qs = Exchange.objects.select_related("book", "owner", "requester")
    status = request.GET.get("status", "")
    if request.GET.get("disputed"):
        qs = qs.filter(status=Exchange.Status.ACCEPTED, disputed_at__isnull=False)
    elif status in Exchange.Status.values:
        qs = qs.filter(status=status)
    qs = search_q(qs, request.GET.get("q"), ["book__title", "owner__username", "requester__username"])
    return page(request, "panel/exchanges.html", {"page": _paginate(request, qs.order_by("-updated_at")), "status": status, "disputed": request.GET.get("disputed", ""),
                                                   "q": request.GET.get("q", ""), "qs": _qs(request), "statuses": Exchange.Status.choices}, "exchanges")


@staff_required
@require_POST
def exchange_resolve(request, pk):
    outcome = request.POST.get("outcome")
    try:
        ex_services.resolve_dispute(pk, request.user, outcome)
    except ex_services.ExchangeError as e:
        fail(request, str(e))
    else:
        log(request, "حل اختلاف: " + ("تکمیل" if outcome == "complete" else "لغو"), f"مبادله #{pk}")
        messages.success(request, "اختلاف حل شد و دو طرف باخبر شدن.")
    return back(request, "panel:exchanges")


# ---------------------------------------------------------------- کاربران
@staff_required
def users(request):
    qs = User.objects.select_related("city").annotate(book_count=Count("books", distinct=True))
    flt = request.GET.get("f", "")
    if flt in User.Status.values:
        qs = qs.filter(status=flt)
    elif flt == "staff":
        qs = qs.filter(is_staff=True)
    elif flt == "new":
        qs = qs.filter(date_joined__gte=timezone.now() - timedelta(days=7))
    elif flt == "warned":
        qs = qs.filter(warnings__gt=0)
    qs = search_q(qs, request.GET.get("q"), ["username", "email"])
    return page(request, "panel/users.html", {"page": _paginate(request, qs.order_by("-date_joined")), "f": flt, "q": request.GET.get("q", ""),
                                               "qs": _qs(request), "user_tabs": USER_TABS, "keep_f": {"f": flt} if flt else {}}, "users")


@staff_required
def user_detail(request, pk):
    u = get_object_or_404(User.objects.select_related("city__province"), pk=pk)
    ctx = {
        "u": u, "rep": reputation(u), "manageable": can_manage(request.user, u),
        "actions": USER_ACTIONS,
        "books": u.books.order_by("-created_at")[:8],
        "exchanges": Exchange.objects.filter(Q(owner=u) | Q(requester=u)).select_related("book").order_by("-created_at")[:8],
        "against": Report.objects.filter(Q(target_user=u) | Q(target_book__owner=u) | Q(target_post__author=u)).order_by("-created_at")[:8],
        "cancels": Exchange.objects.filter(cancelled_by=u).select_related("book").order_by("-cancelled_at")[:5],
        "made": u.reports_made.order_by("-created_at")[:5], "tickets": u.tickets.all()[:5],
        "logs": AuditLog.objects.filter(target__startswith=f"کاربر {u.username}")[:8],
    }
    return page(request, "panel/user_detail.html", ctx, "users")


@staff_required
@require_POST
def user_action(request, pk):
    u = get_object_or_404(User, pk=pk)
    do = request.POST.get("do")
    if not can_manage(request.user, u):
        fail(request, "روی این حساب اجازه‌ی اقدام نداری.")
        return redirect("panel:user", pk)
    form = PointsForm(request.POST) if do == "points" else NoteForm(request.POST)
    if do not in {"warn", "restrict", "ban", "lift", "points"} or (do != "lift" and not form.is_valid()):
        fail(request, "دلیل (و برای امتیاز، عدد معتبر) لازمه.")
        return redirect("panel:user", pk)
    note = form.cleaned_data.get("note", "") if do != "lift" else request.POST.get("note", "").strip()[:300]
    target = f"کاربر {u.username}"
    if do == "warn":
        u.warnings += 1
        notify(u, f"اخطار از مدیریت: {note}", kind="report")
    elif do == "restrict":
        _restrict(u)
        notify(u, f"حساب تو موقتاً محدود شد (فقط کتاب می‌تونی بدی): {note}", kind="report")
    elif do == "ban":
        u.status, u.is_active = User.Status.BANNED, False
    elif do == "lift":
        u.status, u.restricted_until, u.is_active = User.Status.ACTIVE, None, True
        notify(u, "محدودیت حساب تو برداشته شد.", kind="report")
    elif do == "points":
        delta = form.cleaned_data["delta"]
        points.apply(u, delta, "admin_adjust", note=f"{request.user.username}: {note}")
        notify(u, f"مدیریت امتیازت رو {'+' if delta > 0 else ''}{delta} تغییر داد: {note}", kind="report")
        note = f"{delta:+d}؛ {note}"
    u.save()
    labels = {"warn": "اخطار", "restrict": "محدودیت", "ban": "مسدودسازی", "lift": "رفع محدودیت", "points": "تغییر امتیاز"}
    log(request, labels[do], target, note)
    messages.success(request, f"«{labels[do]}» انجام شد.")
    return redirect("panel:user", pk)


@staff_required
@require_POST
def user_reset_link(request, pk):
    """
    ایمیل اختیاریه و بازیابی رمز با ایمیل برای خیلی‌ها کار نمی‌کنه؛ مدیر بعد از احراز هویت کاربر (مثلاً از کانال پشتیبانی)
    یه لینک یک‌بارمصرف می‌سازه و خودش برای کاربر می‌فرسته. لینک با تغییر رمز یا بعد از PASSWORD_RESET_TIMEOUT (پیش‌فرض ۳ روز) باطل می‌شه.
    """
    from django.contrib.auth.tokens import default_token_generator
    from django.urls import reverse
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    u = get_object_or_404(User, pk=pk)
    if not can_manage(request.user, u) or u.is_deleted or not u.is_active:
        fail(request, "برای این حساب نمی‌شه لینک بازیابی ساخت.")
        return redirect("panel:user", pk)
    url = request.build_absolute_uri(reverse("accounts:password_reset_confirm", args=[urlsafe_base64_encode(force_bytes(u.pk)), default_token_generator.make_token(u)]))
    log(request, "ساخت لینک بازیابی رمز", f"کاربر {u.username}")
    messages.success(request, f"لینک بازیابی (۳ روز اعتبار؛ فقط برای خود کاربر بفرست): {url}")
    return redirect("panel:user", pk)


# ---------------------------------------------------------------- کتاب‌ها
@staff_required
def books(request):
    qs = Book.all_objects.select_related("owner", "city")
    status = request.GET.get("status", "")
    if status == "deleted":
        qs = qs.filter(deleted_at__isnull=False)
    else:
        qs = qs.filter(deleted_at__isnull=True)
        if status in Book.Status.values:
            qs = qs.filter(status=status)
    qs = search_q(qs, request.GET.get("q"), ["title", "author", "isbn", "owner__username"])
    return page(request, "panel/books.html", {"page": _paginate(request, qs.order_by("-created_at")), "status": status, "q": request.GET.get("q", ""),
                                               "qs": _qs(request), "statuses": [*Book.Status.choices, ("deleted", "حذف‌شده")], "keep_status": {"status": status} if status else {},
                                               "bulk_url": reverse("panel:books_bulk"), "bulk_opts": [("delete", "حذف (پنهان از سایت)"), ("restore", "بازگردانی")]}, "books")


@staff_required
@require_POST
def book_delete(request, pk):
    book = get_object_or_404(Book.all_objects, pk=pk)
    if book.exchanges.filter(status__in=Exchange.ACTIVE).exists():
        fail(request, "این کتاب مبادله‌ی در جریان داره؛ اول اون رو تموم یا لغو کن.")
    else:
        title, owner = book.title, book.owner
        log(request, "حذف کتاب", f"کتاب «{title}» ({owner.username})", request.POST.get("note", ""))
        book.soft_delete()
        notify(owner, f"کتاب «{title}» از سایت حذف شد." + (f" دلیل: {request.POST['note']}" if request.POST.get("note") else ""), kind="report")
        messages.success(request, "کتاب حذف شد.")
    return back(request, "panel:books")


@staff_required
@require_POST
def book_restore(request, pk):
    book = get_object_or_404(Book.all_objects, pk=pk)
    book.restore()
    log(request, "بازگردانی کتاب", f"کتاب «{book.title}»")
    messages.success(request, "کتاب برگشت.")
    return back(request, "panel:books")


# ---------------------------------------------------------------- عملیات گروهی
BULK_MAX = 100


def _bulk_ids(request):
    ids = [int(i) for i in request.POST.getlist("ids") if str(i).isdigit()][:BULK_MAX]
    if not ids:
        fail(request, "چیزی انتخاب نشده.")
    return ids


@staff_required
@require_POST
def books_bulk(request):
    ids, do, note = _bulk_ids(request), request.POST.get("do"), request.POST.get("note", "").strip()
    done = 0
    for book in Book.all_objects.filter(pk__in=ids).select_related("owner"):
        if do == "delete" and not book.deleted_at and not book.exchanges.filter(status__in=Exchange.ACTIVE).exists():
            book.soft_delete()
            notify(book.owner, f"کتاب «{book.title}» از سایت حذف شد." + (f" دلیل: {note}" if note else ""), kind="report")
            done += 1
        elif do == "restore" and book.deleted_at:
            book.restore()
            done += 1
    if done:
        log(request, {"delete": "حذف گروهی کتاب", "restore": "بازگردانی گروهی کتاب"}.get(do, do), f"{done} کتاب", note)
    messages.success(request, f"{done} کتاب انجام شد." if done else "موردی تغییر نکرد (کتاب‌های در مبادله رد می‌شن).")
    return back(request, "panel:books")


@staff_required
@require_POST
def posts_bulk(request):
    ids, do = _bulk_ids(request), request.POST.get("do")
    done = 0
    for post in Post.objects.filter(pk__in=ids):
        if do == "approve" and post.status != Post.Status.PUBLISHED:
            post_services.publish(post)
            done += 1
    if done:
        log(request, "تأیید گروهی معرفی", f"{done} معرفی")
    messages.success(request, f"{done} معرفی تأیید شد.")
    return back(request, "panel:posts")


@staff_required
@require_POST
def announcements_bulk(request):
    ids, do = _bulk_ids(request), request.POST.get("do")
    done = 0
    for item in Announcement.objects.filter(pk__in=ids):
        if do == "approve" and item.status != Announcement.Status.PUBLISHED:
            ann_services.publish(item)
            done += 1
    if done:
        log(request, "تأیید گروهی اطلاعیه", f"{done} اطلاعیه")
    messages.success(request, f"{done} اطلاعیه تأیید شد.")
    return back(request, "panel:announcements")


# ---------------------------------------------------------------- نویسنده/ناشر تکراری
@staff_required
def names(request):
    from books.authors import duplicate_pairs

    kind = "publisher" if request.GET.get("kind") == "publisher" else "author"
    return page(request, "panel/names.html", {"kind": kind, "pairs": duplicate_pairs(kind)}, "names")


@staff_required
@require_POST
def names_merge(request):
    from books.authors import merge

    kind = "publisher" if request.POST.get("kind") == "publisher" else "author"
    drop, keep = request.POST.get("drop", "").strip(), request.POST.get("keep", "").strip()
    if not drop or not keep:
        fail(request, "ادغام ناقصه.")
    else:
        n = merge(kind, drop, keep)
        log(request, "ادغام " + ("ناشر" if kind == "publisher" else "نویسنده"), f"«{drop}» ← «{keep}»", f"{n} ردیف")
        messages.success(request, f"ادغام شد؛ {n} ردیف به «{keep}» تغییر کرد.")
    return redirect(reverse("panel:names") + ("?kind=publisher" if kind == "publisher" else ""))


# ---------------------------------------------------------------- باشگاه‌ها
@staff_required
def clubs(request):
    from clubs.models import Club

    status = request.GET.get("status", "")
    qs = Club.objects.select_related("owner", "city").annotate(n=Count("members", distinct=True), msgs=Count("posts", distinct=True))
    if status == "inactive":
        qs = qs.filter(is_active=False)
    elif status == "active":
        qs = qs.filter(is_active=True)
    qs = search_q(qs, request.GET.get("q"), ["name", "owner__username", "current_title"])
    return page(request, "panel/clubs.html", {"page": _paginate(request, qs.order_by("-created_at")), "status": status, "q": request.GET.get("q", ""),
                                               "qs": _qs(request), "keep_status": {"status": status} if status else {},
                                               "bulk_url": reverse("panel:clubs_bulk"), "bulk_opts": [("deactivate", "غیرفعال‌سازی"), ("activate", "فعال‌سازی")]}, "clubs")


@staff_required
@require_POST
def clubs_bulk(request):
    from clubs.models import Club

    ids, do = _bulk_ids(request), request.POST.get("do")
    if do in ("activate", "deactivate"):
        n = Club.objects.filter(pk__in=ids).update(is_active=(do == "activate"))
        log(request, "فعال‌سازی باشگاه" if do == "activate" else "غیرفعال‌سازی باشگاه", f"{n} باشگاه", request.POST.get("note", ""))
        messages.success(request, f"{n} باشگاه به‌روز شد.")
    return back(request, "panel:clubs")


# ---------------------------------------------------------------- معرفی‌ها
@staff_required
def posts(request):
    status = request.GET.get("status", "pending")
    qs = Post.objects.select_related("author", "book")
    if status in Post.Status.values:
        qs = qs.filter(status=status)
    qs = search_q(qs, request.GET.get("q"), ["title", "author__username"])
    return page(request, "panel/posts.html", {"page": _paginate(request, qs.order_by("-created_at")), "status": status, "q": request.GET.get("q", ""),
                                               "qs": _qs(request), "item_tabs": list(Post.Status.choices), "keep_status": {"status": status},
                                               "bulk_url": reverse("panel:posts_bulk"), "bulk_opts": [("approve", "تأیید و انتشار")]}, "posts")


@staff_required
@require_POST
def post_action(request, pk):
    post = get_object_or_404(Post, pk=pk)
    do, note = request.POST.get("do"), request.POST.get("note", "").strip()
    if do == "approve":
        post_services.publish(post)
    elif do == "reject" and note:
        post_services.reject(post, note)
    elif do == "feature":
        post.is_featured = not post.is_featured
        post.save(update_fields=["is_featured"])
    elif do == "delete":
        log(request, "حذف معرفی", f"«{post.title}»", note)
        post.delete()
        messages.success(request, "حذف شد.")
        return back(request, "panel:posts")
    else:
        fail(request, "برای رد کردن، دلیل لازمه.")
        return back(request, "panel:posts")
    log(request, {"approve": "تأیید معرفی", "reject": "رد معرفی", "feature": "ویژه‌کردن معرفی"}[do], f"«{post.title}»", note)
    messages.success(request, "انجام شد.")
    return back(request, "panel:posts")


# ---------------------------------------------------------------- اطلاعیه‌ها
@staff_required
def announcements(request):
    status = request.GET.get("status", "pending")
    qs = Announcement.objects.select_related("submitted_by", "city")
    if status in Announcement.Status.values:
        qs = qs.filter(status=status)
    qs = search_q(qs, request.GET.get("q"), ["title", "submitted_by__username"])
    return page(request, "panel/announcements.html", {"page": _paginate(request, qs.order_by("-created_at")), "status": status, "q": request.GET.get("q", ""),
                                                       "qs": _qs(request), "item_tabs": list(Announcement.Status.choices), "keep_status": {"status": status},
                                                       "bulk_url": reverse("panel:announcements_bulk"), "bulk_opts": [("approve", "تأیید و انتشار")]}, "announcements")


@staff_required
@require_POST
def announcement_action(request, pk):
    item = get_object_or_404(Announcement, pk=pk)
    do, note = request.POST.get("do"), request.POST.get("note", "").strip()
    if do == "approve":
        ann_services.publish(item)
    elif do == "reject" and note:
        ann_services.reject(item, note)
    elif do == "feature":
        item.is_featured = not item.is_featured
        item.save(update_fields=["is_featured"])
    elif do == "delete":
        log(request, "حذف اطلاعیه", f"«{item.title}»", note)
        item.delete()
        messages.success(request, "حذف شد.")
        return back(request, "panel:announcements")
    else:
        fail(request, "برای رد کردن، دلیل لازمه.")
        return back(request, "panel:announcements")
    log(request, {"approve": "تأیید اطلاعیه", "reject": "رد اطلاعیه", "feature": "ویژه‌کردن اطلاعیه"}[do], f"«{item.title}»", note)
    messages.success(request, "انجام شد.")
    return back(request, "panel:announcements")


# ---------------------------------------------------------------- چالش‌ها
@staff_required
def challenges(request):
    return page(request, "panel/challenges.html", {"items": Challenge.objects.all(), "now": timezone.now()}, "challenges")


@staff_required
def challenge_form(request, pk=None):
    item = get_object_or_404(Challenge, pk=pk) if pk else None
    form = ChallengeForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        log(request, "ویرایش چالش" if item else "ساخت چالش", f"«{c.title}»")
        messages.success(request, "چالش ذخیره شد.")
        return redirect("panel:challenges")
    return page(request, "panel/challenge_form.html", {"form": form, "item": item}, "challenges")


@staff_required
@require_POST
def challenge_action(request, pk):
    c = get_object_or_404(Challenge, pk=pk)
    if request.POST.get("do") == "delete":
        log(request, "حذف چالش", f"«{c.title}»")
        c.delete()
    else:
        c.is_active = not c.is_active
        c.save(update_fields=["is_active"])
        log(request, "فعال‌سازی چالش" if c.is_active else "غیرفعال‌سازی چالش", f"«{c.title}»")
    return redirect("panel:challenges")


# ---------------------------------------------------------------- تنظیمات و لاگ
@staff_required
def settings_view(request):
    form = SiteSettingForm(request.POST or None, instance=SiteSetting.load())
    if request.method == "POST" and form.is_valid():
        form.save()
        log(request, "ویرایش تنظیمات سایت", "، ".join(form.changed_data))
        messages.success(request, "تنظیمات ذخیره شد.")
        return redirect("panel:settings")
    return page(request, "panel/settings.html", {"form": form}, "settings")


@staff_required
def audit(request):
    qs = search_q(AuditLog.objects.select_related("actor"), request.GET.get("q"), ["action", "target", "note", "actor__username"])
    return page(request, "panel/audit.html", {"page": _paginate(request, qs), "q": request.GET.get("q", ""), "qs": _qs(request)}, "audit")
