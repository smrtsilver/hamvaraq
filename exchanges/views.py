from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from books.models import Book, BookNote
from trust.forms import VoteForm
from trust.models import Vote
from trust.services import can_edit_vote

from . import services
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


accept = _action(services.accept, "درخواست تأیید شد.")
reject = _action(services.reject, "درخواست رد شد.")
cancel = _action(services.cancel, "مبادله لغو شد.")
confirm = _action(services.confirm, "تأییدت ثبت شد.")


@login_required
def exchange_list(request):
    qs = Exchange.objects.filter(Q(owner=request.user) | Q(requester=request.user)).select_related("book", "owner", "requester")
    return render(request, "exchanges/list.html", {"exchanges": qs})


@login_required
def exchange_detail(request, pk):
    ex = get_object_or_404(Exchange.objects.select_related("book", "owner", "requester"), pk=pk)
    if not ex.is_party(request.user):
        return render(request, "404.html", status=404)
    my_vote = Vote.objects.filter(exchange=ex, voter=request.user).first()
    ctx = {
        "ex": ex,
        "other": ex.other_party(request.user),
        "is_owner": ex.owner_id == request.user.pk,
        "chat": ex.messages.select_related("sender"),
        "chat_open": ex.status in (*Exchange.ACTIVE, Exchange.Status.COMPLETED),
        "my_vote": my_vote,
        "vote_form": VoteForm(instance=my_vote) if ex.status == Exchange.Status.COMPLETED and (not my_vote or can_edit_vote(my_vote)) else None,
        "can_note": ex.status == Exchange.Status.COMPLETED and ex.owner_id == request.user.pk and not hasattr(ex, "note"),
    }
    return render(request, "exchanges/detail.html", ctx)


@login_required
@require_POST
def send_message(request, pk):
    ex = get_object_or_404(Exchange, pk=pk)
    text = request.POST.get("text", "").strip()[:1000]
    if not ex.is_party(request.user):
        return redirect("home")
    if text and ex.status in (*Exchange.ACTIVE, Exchange.Status.COMPLETED):
        from notifications.services import notify

        Message.objects.create(exchange=ex, sender=request.user, text=text)
        notify(ex.other_party(request.user), f"پیام تازه از {request.user.username}", f"/exchanges/{ex.pk}/")
    return redirect("exchanges:detail", pk)


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
