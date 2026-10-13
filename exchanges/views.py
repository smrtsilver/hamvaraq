from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from books.models import Book, BookNote
from trust.forms import VoteForm
from trust.models import Vote
from trust.services import can_edit_vote

from common.throttle import throttle

from . import chat, services
from .forms import DisputeForm
from .models import Exchange, Message


def _run(request, action, *args):
    try:
        return action(*args)
    except services.ExchangeError as e:
        messages.error(request, str(e))
    except (Book.DoesNotExist, Exchange.DoesNotExist):
        messages.error(request, "مورد پیدا نشد.")
    return None


@login_required
@throttle("request", 20, 86400, by="user")
@require_POST
def request_book(request, book_id):
    ex = _run(request, services.request_book, book_id, request.user)
    if ex:
        messages.success(request, "درخواستت ثبت شد و ۱ امتیاز نگه داشته شد.")
        return redirect("exchanges:detail", ex.pk)
    return redirect("books:detail", book_id)


def _action(service, ok_message):
    @login_required
    @require_POST
    def view(request, pk):
        if _run(request, service, pk, request.user):
            messages.success(request, ok_message)
        return redirect("exchanges:detail", pk)

    return view


@login_required
@require_POST
@throttle("postal", 20, 3600, by="user")
def postal(request, pk):
    if _run(request, services.set_postal, pk, request.user, request.POST.get("tracking_code", "")):
        messages.success(request, "ارسال پستی ثبت شد و گیرنده خبردار شد.")
    return redirect("exchanges:detail", pk)


accept = _action(services.accept, "درخواست تأیید شد.")
reject = _action(services.reject, "درخواست رد شد.")
@login_required
@require_POST
def cancel(request, pk):
    """لغو با دلیل اختیاری (فهرست ثابت یا متن آزاد کوتاه)."""
    reason = request.POST.get("reason", "")
    if _run(request, services.cancel, pk, request.user, reason):
        messages.success(request, "مبادله لغو شد.")
    return redirect("exchanges:detail", pk)

confirm = _action(services.confirm, "تأییدت ثبت شد.")


@login_required
@require_POST
def propose_meeting(request, pk):
    if _run(request, services.propose_meeting, pk, request.user, request.POST.get("point") or 0):
        messages.success(request, "پیشنهادت برای نقطه‌ی تحویل ارسال شد.")
    return redirect("exchanges:detail", pk)


agree_meeting = _action(services.agree_meeting, "نقطه‌ی تحویل تأیید شد.")


@login_required
@throttle("dispute", 5, 86400, by="user")
@require_POST
def dispute(request, pk):
    form = DisputeForm(request.POST)
    if form.is_valid() and _run(request, services.open_dispute, pk, request.user,
                                form.cleaned_data["reason"], form.cleaned_data["description"]):
        messages.success(request, "اختلاف ثبت شد؛ مدیریت بررسی می‌کنه.")
    elif not form.is_valid():
        messages.error(request, "دلیل مشکل رو انتخاب کن.")
    return redirect("exchanges:detail", pk)


@login_required
def exchange_list(request):
    qs = chat.with_unread(
        Exchange.objects.filter(Q(owner=request.user) | Q(requester=request.user)).select_related("book", "owner", "requester"),
        request.user,
    )
    rows = list(qs)
    for e in rows:
        e.unread = chat.unread_of(e)
    return render(request, "exchanges/list.html", {"exchanges": rows})


@login_required
def exchange_detail(request, pk):
    ex = get_object_or_404(Exchange.objects.select_related("book", "owner", "requester"), pk=pk)
    if not ex.is_party(request.user):
        return render(request, "404.html", status=404)
    my_vote = Vote.objects.filter(exchange=ex, voter=request.user).first()
    chat_messages = list(ex.messages.select_related("sender"))
    chat.mark_read(ex, request.user)
    ctx = {
        "last_message_id": chat_messages[-1].pk if chat_messages else 0,
        "ex": ex,
        "other": ex.other_party(request.user),
        "is_owner": ex.owner_id == request.user.pk,
        "chat": chat_messages,
        "chat_open": ex.status in (*Exchange.ACTIVE, Exchange.Status.COMPLETED),
        "my_vote": my_vote,
        "dispute_form": DisputeForm() if ex.status == Exchange.Status.ACCEPTED and not ex.disputed_at else None,
        "meeting_options": services.meeting_options(ex) if ex.status == Exchange.Status.ACCEPTED else [],
        "vote_form": VoteForm(instance=my_vote) if ex.status == Exchange.Status.COMPLETED and (not my_vote or can_edit_vote(my_vote)) else None,
        "can_note": ex.status == Exchange.Status.COMPLETED and ex.owner_id == request.user.pk and not hasattr(ex, "note"),
    }
    return render(request, "exchanges/detail.html", ctx)


def _message_json(m, user):
    from django.urls import reverse

    from common.jalali import jtime

    return {
        "id": m.pk, "sender": m.sender.public_name, "mine": m.sender_id == user.pk, "text": m.text,
        "time": jtime(m.created_at),
        "report_url": "" if m.sender_id == user.pk else reverse("trust:report", args=["message", m.pk]),
    }


@login_required
@throttle("chat", 30, 600, by="user", json=True)
@require_POST
def send_message(request, pk):
    ex = get_object_or_404(Exchange, pk=pk)
    text = request.POST.get("text", "").strip()[:1000]
    ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    if not ex.is_party(request.user):
        return redirect("home")
    if text and ex.status in (*Exchange.ACTIVE, Exchange.Status.COMPLETED):
        from notifications.models import Notification
        from notifications.services import notify

        Message.objects.create(exchange=ex, sender=request.user, text=text)
        other, url = ex.other_party(request.user), f"/exchanges/{ex.pk}/"
        # پشت‌سرهم پیام دادن اعلان تکراری نمی‌سازه؛ شمارنده‌ی خوانده‌نشده‌ی چت کافیه
        if not Notification.objects.filter(user=other, url=url, is_read=False, text__startswith="پیام تازه").exists():
            notify(other, f"پیام تازه از {request.user.public_name}", url, kind="chat")
    if ajax:
        return JsonResponse({"ok": bool(text)})
    return redirect("exchanges:detail", pk)


@login_required
def poll_messages(request, pk):
    """پیام‌های تازه‌تر از `after` (شناسه). جاوااسکریپت چت هر چند ثانیه صداش می‌زنه."""
    ex = get_object_or_404(Exchange, pk=pk)
    if not ex.is_party(request.user):
        return JsonResponse({"error": "forbidden"}, status=403)
    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        after = 0
    new = list(ex.messages.filter(pk__gt=after).select_related("sender")[:100])
    if new:
        chat.mark_read(ex, request.user)
    return JsonResponse({
        "messages": [_message_json(m, request.user) for m in new],
        "status": ex.status,
    })


@login_required
@require_POST
def add_note(request, pk):
    """صاحب قبلی بعد از تحویل یه جمله برای خواننده‌ی بعدی می‌نویسه."""
    ex = get_object_or_404(Exchange, pk=pk, owner=request.user, status=Exchange.Status.COMPLETED)
    text = request.POST.get("text", "").strip()[:500]
    if text and not hasattr(ex, "note"):
        BookNote.objects.create(book=ex.book, author=request.user, exchange=ex, text=text)
        messages.success(request, "یادداشتت تو کتاب ثبت شد.")
    return redirect("exchanges:detail", pk)
