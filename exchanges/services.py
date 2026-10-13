"""منطق مبادله. همه‌ی تغییر امتیاز و وضعیت کتاب فقط از این‌جا انجام می‌شه."""

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.badges import check_badges
from accounts.models import User
from common import points
from books.models import Book, BookJourney
from notifications.models import Notification
from notifications.services import notify as _notify

from .models import Exchange


def notify(user, text, url=""):
    return _notify(user, text, url, kind=Notification.Kind.EXCHANGE)


class ExchangeError(Exception):
    """پیام خطا برای نمایش به کاربر."""


def _url(exchange):
    return reverse("exchanges:detail", args=[exchange.pk])


@transaction.atomic
def request_book(book_id, requester):
    """امتیاز درخواست‌دهنده همون لحظه نگه داشته می‌شه تا خرجِ چند درخواست نشه."""
    try:
        book = Book.all_objects.select_for_update().select_related("owner").get(pk=book_id)
    except Book.DoesNotExist:
        raise ExchangeError("این کتاب پیدا نشد.") from None
    if book.is_deleted:
        raise ExchangeError("این کتاب دیگه تو سایت نیست.")
    owner = book.owner
    if not owner.is_active or owner.status == User.Status.BANNED:
        raise ExchangeError("صاحب این کتاب الان نمی‌تونه مبادله انجام بده.")
    requester = User.objects.select_for_update().get(pk=requester.pk)
    if book.owner_id == requester.pk:
        raise ExchangeError("کتاب خودت رو نمی‌تونی درخواست بدی.")
    if not requester.can_request:
        raise ExchangeError("حساب تو الان اجازه‌ی گرفتن کتاب نداره.")
    if book.status != Book.Status.AVAILABLE:
        raise ExchangeError("این کتاب الان موجود نیست.")
    if requester.points < 1:
        raise ExchangeError("امتیاز کافی نداری؛ اول یه کتاب بده تا امتیاز بگیری.")
    # با امتیاز هدیه‌ی یه حساب فیک نمی‌شه از حساب هم‌شبکه‌ی خودش کتاب گرفت؛ اول باید به یه نفر کتاب داده باشه
    if requester.is_linked_to(book.owner) and not Exchange.objects.filter(owner=requester, status=Exchange.Status.COMPLETED).exists():
        raise ExchangeError("این کتاب مال کسیه که از همین شبکه‌ی اینترنت وارد می‌شه. اول یه کتاب به یه نفر دیگه بده، بعد می‌تونی از ایشون هم بگیری.")
    if Exchange.objects.filter(book=book, requester=requester, status__in=Exchange.ACTIVE).exists():
        raise ExchangeError("برای این کتاب قبلاً درخواست دادی.")
    exchange = Exchange.objects.create(book=book, requester=requester, owner=book.owner)
    points.apply(requester, -1, "request_hold", exchange=exchange, note=book.title)
    notify(book.owner, f"{requester.public_name} کتاب «{book.title}» رو درخواست داد.", _url(exchange))
    return exchange


def _refund(exchange):
    points.apply(exchange.requester_id, +1, "request_refund", exchange=exchange, note=exchange.book.title)


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
    ex.accepted_at, ex.reminder_count = timezone.now(), 0
    ex.save(update_fields=["status", "accepted_at", "reminder_count", "updated_at"])
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
def cancel(exchange_id, user, reason=""):
    """لغو توسط یکی از دو طرف؛ لغوکننده و دلیلش ثبت می‌شه (لغو بعد از تأیید برای تحلیل اعتماد مهمه)."""
    ex = _get_locked(exchange_id)
    if not ex.is_party(user):
        raise ExchangeError("این مبادله مال تو نیست.")
    if ex.status not in Exchange.ACTIVE:
        raise ExchangeError("این مبادله دیگه قابل لغو نیست.")
    was_accepted = ex.status == Exchange.Status.ACCEPTED
    ex.status = Exchange.Status.CANCELLED
    ex.cancelled_by, ex.cancelled_at, ex.cancel_reason = user, timezone.now(), " ".join((reason or "").split())[:200]
    ex.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason", "updated_at"])
    _refund(ex)
    if was_accepted:
        ex.book.status = Book.Status.AVAILABLE
        ex.book.save(update_fields=["status"])
    notify(ex.other_party(user), f"مبادله‌ی «{ex.book.title}» لغو شد." + (f" دلیل: {ex.cancel_reason}" if ex.cancel_reason else ""), _url(ex))
    return ex


@transaction.atomic
def set_postal(exchange_id, user, tracking_code):
    """صاحب کتاب (فرستنده) ارسال پستی رو با کد رهگیری ثبت می‌کنه؛ گیرنده خبردار می‌شه و بعد از رسیدن «تحویل انجام شد» رو می‌زنه."""
    import re

    from common.text import normalize

    ex = _get_locked(exchange_id)
    if ex.owner_id != user.pk:
        raise ExchangeError("فقط صاحب کتاب می‌تونه ارسال پستی ثبت کنه.")
    if ex.status != Exchange.Status.ACCEPTED:
        raise ExchangeError("ارسال فقط برای مبادله‌ی تأییدشده ثبت می‌شه.")
    code = re.sub(r"[\s-]", "", normalize(tracking_code)).upper()
    if not re.fullmatch(r"[A-Z0-9]{8,30}", code):
        raise ExchangeError("کد رهگیری باید ۸ تا ۳۰ حرف و عدد (انگلیسی یا فارسی) باشه.")
    ex.delivery, ex.tracking_code, ex.shipped_at = Exchange.Delivery.POSTAL, code, timezone.now()
    ex.save(update_fields=["delivery", "tracking_code", "shipped_at", "updated_at"])
    notify(ex.requester, f"«{ex.book.title}» با پست ارسال شد. کد رهگیری: {code}. بعد از رسیدن «تحویل انجام شد» رو بزن.", _url(ex))
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
        if ex.first_confirmed_at is None:
            ex.first_confirmed_at, ex.reminder_count = timezone.now(), 0
        ex.save(update_fields=["owner_confirmed", "requester_confirmed", "first_confirmed_at", "reminder_count", "updated_at"])
        notify(ex.other_party(user), f"{user.public_name} تحویل «{ex.book.title}» رو تأیید کرد؛ نوبت توئه.", _url(ex))
    return ex


def _complete(ex):
    giver, receiver, book = ex.owner, ex.requester, ex.book
    ex.status = Exchange.Status.COMPLETED
    ex.completed_at = timezone.now()
    ex.save()
    points.apply(giver.pk, +1, "exchange_reward", exchange=ex, note=book.title)
    BookJourney.objects.create(book=book, exchange=ex, from_city=book.city, to_city=receiver.city)
    book.owner = receiver
    book.status = Book.Status.EXCHANGED
    if receiver.city_id:
        book.city_id = receiver.city_id
    book.save(update_fields=["owner", "status", "city"])
    # قفسه: کتاب از آگهی‌های دهنده جدا می‌شه (خودِ ردیف و نقدش می‌مونه) و به قفسه‌ی گیرنده اضافه می‌شه
    from books.models import ShelfEntry

    ShelfEntry.objects.filter(user=giver, book=book).update(book=None)
    ShelfEntry.objects.get_or_create(user=receiver, book=book, defaults={
        "title": book.title, "author": book.author, "isbn": book.isbn, "edition": book.edition, "reading_status": ShelfEntry.Reading.WANT})
    notify(giver, f"مبادله‌ی «{book.title}» کامل شد؛ ۱ امتیاز گرفتی. به {receiver.public_name} رأی بده.", _url(ex))
    notify(receiver, f"کتاب «{book.title}» مال توئه. به {giver.public_name} رأی بده.", _url(ex))
    check_badges(giver)
    check_badges(receiver)


def meeting_options(exchange):
    """نقطه‌های فعال شهر کتاب و شهر دو طرف."""
    from common.models import MeetingPoint

    city_ids = {c for c in (exchange.book.city_id, exchange.owner.city_id, exchange.requester.city_id) if c}
    return MeetingPoint.objects.filter(city_id__in=city_ids, is_active=True).select_related("city")


@transaction.atomic
def propose_meeting(exchange_id, user, point_id):

    from .models import Message

    ex = _get_locked(exchange_id)
    if not ex.is_party(user):
        raise ExchangeError("این مبادله مال تو نیست.")
    if ex.status != Exchange.Status.ACCEPTED:
        raise ExchangeError("نقطه‌ی تحویل فقط برای مبادله‌ی تأییدشده‌ست.")
    point = meeting_options(ex).filter(pk=point_id).first()
    if not point:
        raise ExchangeError("این نقطه برای این مبادله مجاز نیست.")
    ex.meeting_point, ex.meeting_proposed_by, ex.meeting_agreed = point, user, False
    ex.save(update_fields=["meeting_point", "meeting_proposed_by", "meeting_agreed", "updated_at"])
    Message.objects.create(exchange=ex, sender=user, text=f"📍 پیشنهاد نقطه‌ی تحویل: {point.name} ({point.city})")
    notify(ex.other_party(user), f"{user.public_name} نقطه‌ی تحویل پیشنهاد داد: {point.name}", _url(ex))
    return ex


@transaction.atomic
def agree_meeting(exchange_id, user):
    from .models import Message

    ex = _get_locked(exchange_id)
    if not ex.is_party(user):
        raise ExchangeError("این مبادله مال تو نیست.")
    if ex.status != Exchange.Status.ACCEPTED or not ex.meeting_point_id:
        raise ExchangeError("نقطه‌ای برای تأیید نیست.")
    if ex.meeting_proposed_by_id == user.pk:
        raise ExchangeError("پیشنهاد خودت رو باید طرف مقابل تأیید کنه.")
    if ex.meeting_agreed:
        return ex
    ex.meeting_agreed = True
    ex.save(update_fields=["meeting_agreed", "updated_at"])
    Message.objects.create(exchange=ex, sender=user, text=f"✅ نقطه‌ی تحویل تأیید شد: {ex.meeting_point.name}")
    notify(ex.other_party(user), f"{user.public_name} نقطه‌ی تحویل رو تأیید کرد: {ex.meeting_point.name}", _url(ex))
    return ex


# ---------- انقضا، یادآوری و اختلاف ----------

def auto_cancel(ex, reason):
    """لغو توسط سیستم (بدون کاربر): امتیاز برمی‌گرده و کتاب دوباره موجود می‌شه."""
    with transaction.atomic():
        ex = _get_locked(ex.pk)
        if ex.status not in Exchange.ACTIVE:
            return ex
        was_accepted = ex.status == Exchange.Status.ACCEPTED
        ex.status = Exchange.Status.CANCELLED
        ex.cancelled_by, ex.cancelled_at, ex.cancel_reason = None, timezone.now(), f"سیستم: {reason}"[:200]
        ex.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason", "updated_at"])
        _refund(ex)
        if was_accepted:
            ex.book.status = Book.Status.AVAILABLE
            ex.book.save(update_fields=["status"])
        notify(ex.requester, f"مبادله‌ی «{ex.book.title}» {reason}؛ امتیازت برگشت.", _url(ex))
        notify(ex.owner, f"مبادله‌ی «{ex.book.title}» {reason}.", _url(ex))
    return ex


def _open_dispute(ex, reporter, accused, reason, description):
    """اختلاف رو به‌صورت گزارش برای ادمین ثبت می‌کنه و مبادله رو از انقضای خودکار خارج می‌کنه."""
    from trust.models import Report

    Report.objects.get_or_create(
        reporter=reporter, target_user=accused,
        defaults={"reason": reason, "description": f"[اختلاف در مبادله #{ex.pk} — «{ex.book.title}»] {description}".strip()},
    )
    ex.disputed_at = timezone.now()
    ex.save(update_fields=["disputed_at", "updated_at"])
    notify(accused, f"برای مبادله‌ی «{ex.book.title}» اختلاف ثبت شد؛ مدیریت بررسی می‌کنه.", _url(ex))
    notify(reporter, f"اختلاف مبادله‌ی «{ex.book.title}» ثبت شد؛ مدیریت بررسی می‌کنه.", _url(ex))


@transaction.atomic
def open_dispute(exchange_id, user, reason, description=""):
    ex = _get_locked(exchange_id)
    if not ex.is_party(user):
        raise ExchangeError("این مبادله مال تو نیست.")
    if ex.status != Exchange.Status.ACCEPTED:
        raise ExchangeError("اختلاف فقط برای مبادله‌ی تأییدشده‌ی تموم‌نشده ثبت می‌شه.")
    if ex.disputed_at:
        raise ExchangeError("برای این مبادله قبلاً اختلاف ثبت شده.")
    _open_dispute(ex, user, ex.other_party(user), reason, description)
    return ex


@transaction.atomic
def resolve_dispute(exchange_id, admin_user, outcome):
    """تصمیم ادمین: «complete» (تحویل انجام شده) یا «cancel» (مبادله لغو و امتیاز برگردونده می‌شه)."""
    ex = _get_locked(exchange_id)
    if not ex.disputed_at or ex.status != Exchange.Status.ACCEPTED:
        raise ExchangeError("این مبادله اختلاف بازی نداره.")
    ex.resolution_note = f"{'تکمیل' if outcome == 'complete' else 'لغو'} توسط {admin_user.username}"
    if outcome == "complete":
        ex.owner_confirmed = ex.requester_confirmed = True
        _complete(ex)
    elif outcome == "cancel":
        auto_cancel(ex, "به‌خاطر اختلاف توسط مدیریت لغو شد")
        Exchange.objects.filter(pk=ex.pk).update(resolution_note=ex.resolution_note)
    else:
        raise ExchangeError("نتیجه‌ی نامعتبر.")
    return ex


def process_lifecycle(now=None, dry_run=False):
    """
    یک دور بررسی همه‌ی مبادله‌های فعال. شمارنده‌ی نتیجه رو برمی‌گردونه.
    با اجرای دوباره در همون روز اعلان تکراری نمی‌سازه (reminder_count).
    """
    from datetime import timedelta

    from django.conf import settings

    now = now or timezone.now()
    out = {"reminded": 0, "cancelled": 0, "disputed": 0, "relist_reminded": 0}

    def days(since):
        return (now - since) / timedelta(days=1)

    def remind(ex, schedule, since, targets, text):
        if ex.reminder_count < len(schedule) and days(since) >= schedule[ex.reminder_count]:
            out["reminded"] += 1
            if not dry_run:
                for user in targets:
                    notify(user, text, _url(ex))
                Exchange.objects.filter(pk=ex.pk).update(reminder_count=ex.reminder_count + 1)

    base = Exchange.objects.select_related("book", "owner", "requester")
    for ex in base.filter(status=Exchange.Status.REQUESTED):
        age = days(ex.created_at)
        if age >= settings.REQUEST_EXPIRE_DAYS:
            out["cancelled"] += 1
            if not dry_run:
                auto_cancel(ex, "بی‌پاسخ موند و منقضی شد")
        else:
            remind(ex, settings.REQUEST_REMIND_DAYS, ex.created_at, [ex.owner],
                   f"درخواست «{ex.book.title}» هنوز منتظر جواب توئه.")

    for ex in base.filter(status=Exchange.Status.ACCEPTED, disputed_at__isnull=True):
        if ex.first_confirmed_at:
            if days(ex.first_confirmed_at) >= settings.CONFIRM_DISPUTE_DAYS:
                out["disputed"] += 1
                if not dry_run:
                    confirmer_is_owner = ex.owner_confirmed
                    reporter, accused = (ex.owner, ex.requester) if confirmer_is_owner else (ex.requester, ex.owner)
                    _open_dispute(ex, reporter, accused, "other",
                                  "یک طرف تحویل رو تأیید کرده و طرف مقابل در مهلت مقرر پاسخی نداده.")
            else:
                waiting = ex.requester if ex.owner_confirmed else ex.owner
                remind(ex, settings.CONFIRM_REMIND_DAYS, ex.first_confirmed_at, [waiting],
                       f"طرف مقابل تحویل «{ex.book.title}» رو تأیید کرده؛ اگه تحویل شده تأیید کن، وگرنه مشکلت رو ثبت کن.")
        else:
            since = ex.accepted_at or ex.created_at
            if days(since) >= settings.ACCEPTED_EXPIRE_DAYS:
                out["cancelled"] += 1
                if not dry_run:
                    auto_cancel(ex, "بدون تحویل موند و منقضی شد")
            else:
                remind(ex, settings.ACCEPTED_REMIND_DAYS, since, [ex.owner, ex.requester],
                       f"مبادله‌ی «{ex.book.title}» تأیید شده ولی هنوز تحویل نشده؛ هماهنگ کنید یا لغوش کنید.")

    # کتاب گرفته‌شده‌ای که ۷ روز بعد از تحویل هنوز «مبادله‌شده» مونده: یه‌بار یادآوری برای دوباره‌گذاشتن (چرخه‌ی کتاب نمیره)
    cutoff = now - timedelta(days=settings.RELIST_REMIND_DAYS)
    for ex in base.filter(status=Exchange.Status.COMPLETED, completed_at__lte=cutoff, relist_reminded_at__isnull=True,
                          book__status=Book.Status.EXCHANGED):
        if ex.book.owner_id != ex.requester_id:          # کتاب تو این فاصله جابه‌جا شده
            continue
        out["relist_reminded"] += 1
        if not dry_run:
            notify(ex.requester, f"«{ex.book.title}» رو خوندی؟ دوباره برای مبادله بذارش تا نفر بعدی بخونه.",
                   reverse("books:relist", args=[ex.book_id]))
            Exchange.objects.filter(pk=ex.pk).update(relist_reminded_at=now)
    return out
