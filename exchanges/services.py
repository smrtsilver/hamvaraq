"""منطق مبادله. همه‌ی تغییر امتیاز و وضعیت کتاب فقط از این‌جا انجام می‌شه."""

from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from accounts.badges import check_badges
from accounts.models import User
from books.models import Book, BookJourney
from notifications.services import notify

from .models import Exchange


class ExchangeError(Exception):
    """پیام خطا برای نمایش به کاربر."""


def _url(exchange):
    return reverse("exchanges:detail", args=[exchange.pk])


@transaction.atomic
def request_book(book_id, requester):
    """امتیاز درخواست‌دهنده همون لحظه نگه داشته می‌شه تا خرجِ چند درخواست نشه."""
    book = Book.objects.select_for_update().select_related("owner").get(pk=book_id)
    requester = User.objects.select_for_update().get(pk=requester.pk)
    if book.owner_id == requester.pk:
        raise ExchangeError("کتاب خودت رو نمی‌تونی درخواست بدی.")
    if not requester.can_request:
        raise ExchangeError("حساب تو الان اجازه‌ی گرفتن کتاب نداره.")
    if book.status != Book.Status.AVAILABLE:
        raise ExchangeError("این کتاب الان موجود نیست.")
    if requester.points < 1:
        raise ExchangeError("امتیاز کافی نداری؛ اول یه کتاب بده تا امتیاز بگیری.")
    if Exchange.objects.filter(book=book, requester=requester, status__in=Exchange.ACTIVE).exists():
        raise ExchangeError("برای این کتاب قبلاً درخواست دادی.")
    requester.points -= 1
    requester.save(update_fields=["points"])
    exchange = Exchange.objects.create(book=book, requester=requester, owner=book.owner)
    notify(book.owner, f"{requester.username} کتاب «{book.title}» رو درخواست داد.", _url(exchange))
    return exchange


def _refund(exchange):
    User.objects.filter(pk=exchange.requester_id).update(points=F("points") + 1)


def _get_locked(exchange_id):
    return Exchange.objects.select_for_update().select_related("book", "owner", "requester").get(pk=exchange_id)


@transaction.atomic
def accept(exchange_id, user):
    ex = _get_locked(exchange_id)
    if ex.owner_id != user.pk:
        raise ExchangeError("فقط صاحب کتاب می‌تونه تأیید کنه.")
    if ex.status != Exchange.Status.REQUESTED:
        raise ExchangeError("این درخواست دیگه در انتظار تأیید نیست.")
    if ex.book.status != Book.Status.AVAILABLE:
        raise ExchangeError("کتاب دیگه موجود نیست.")
    ex.status = Exchange.Status.ACCEPTED
    ex.save(update_fields=["status", "updated_at"])
    ex.book.status = Book.Status.RESERVED
    ex.book.save(update_fields=["status"])
    # بقیه‌ی درخواست‌ها رد می‌شن و امتیازشون برمی‌گرده
    for other in Exchange.objects.select_for_update().filter(book=ex.book, status=Exchange.Status.REQUESTED).exclude(pk=ex.pk):
        other.status = Exchange.Status.REJECTED
        other.save(update_fields=["status", "updated_at"])
        _refund(other)
        notify(other.requester, f"کتاب «{ex.book.title}» به نفر دیگه‌ای رسید؛ امتیازت برگشت.", _url(other))
    notify(ex.requester, f"درخواستت برای «{ex.book.title}» تأیید شد. حالا هماهنگ کنید.", _url(ex))
    return ex


@transaction.atomic
def reject(exchange_id, user):
    ex = _get_locked(exchange_id)
    if ex.owner_id != user.pk:
        raise ExchangeError("فقط صاحب کتاب می‌تونه رد کنه.")
    if ex.status != Exchange.Status.REQUESTED:
        raise ExchangeError("این درخواست دیگه در انتظار تأیید نیست.")
    ex.status = Exchange.Status.REJECTED
    ex.save(update_fields=["status", "updated_at"])
    _refund(ex)
    notify(ex.requester, f"درخواستت برای «{ex.book.title}» رد شد؛ امتیازت برگشت.", _url(ex))
    return ex


@transaction.atomic
def cancel(exchange_id, user):
    ex = _get_locked(exchange_id)
    if not ex.is_party(user):
        raise ExchangeError("این مبادله مال تو نیست.")
    if ex.status not in Exchange.ACTIVE:
        raise ExchangeError("این مبادله دیگه قابل لغو نیست.")
    was_accepted = ex.status == Exchange.Status.ACCEPTED
    ex.status = Exchange.Status.CANCELLED
    ex.save(update_fields=["status", "updated_at"])
    _refund(ex)
    if was_accepted:
        ex.book.status = Book.Status.AVAILABLE
        ex.book.save(update_fields=["status"])
    notify(ex.other_party(user), f"مبادله‌ی «{ex.book.title}» لغو شد.", _url(ex))
    return ex


@transaction.atomic
def confirm(exchange_id, user):
    """تحویل باید هر دو طرف تأیید کنن؛ با تأیید دومی مبادله کامل می‌شه."""
    ex = _get_locked(exchange_id)
    if not ex.is_party(user):
        raise ExchangeError("این مبادله مال تو نیست.")
    if ex.status != Exchange.Status.ACCEPTED:
        raise ExchangeError("مبادله هنوز تأیید نشده یا تموم شده.")
    if user.pk == ex.owner_id:
        ex.owner_confirmed = True
    else:
        ex.requester_confirmed = True
    if ex.owner_confirmed and ex.requester_confirmed:
        _complete(ex)
    else:
        ex.save(update_fields=["owner_confirmed", "requester_confirmed", "updated_at"])
        notify(ex.other_party(user), f"{user.username} تحویل «{ex.book.title}» رو تأیید کرد؛ نوبت توئه.", _url(ex))
    return ex


def _complete(ex):
    giver, receiver, book = ex.owner, ex.requester, ex.book
    ex.status = Exchange.Status.COMPLETED
    ex.completed_at = timezone.now()
    ex.save()
    User.objects.filter(pk=giver.pk).update(points=F("points") + 1)
    BookJourney.objects.create(book=book, exchange=ex, from_city=book.city, to_city=receiver.city or book.city)
    book.owner = receiver
    book.status = Book.Status.EXCHANGED
    if receiver.city_id:
        book.city_id = receiver.city_id
    book.save(update_fields=["owner", "status", "city"])
    notify(giver, f"مبادله‌ی «{book.title}» کامل شد؛ ۱ امتیاز گرفتی. به {receiver.username} رأی بده.", _url(ex))
    notify(receiver, f"کتاب «{book.title}» مال توئه. به {giver.username} رأی بده.", _url(ex))
    check_badges(giver)
    check_badges(receiver)
