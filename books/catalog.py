"""
کاتالوگ چاپ‌ها (Edition): ترکیب پایگاه داده‌ی خودمون با خط‌لوله‌ی استعلام شابک.

- resolve(): اول Edition ذخیره‌شده (بدون شبکه)، فقط اگه منبع‌دار نبود یا نبود سراغ منبع‌های بیرونی می‌ره.
- record_user_entry(): داده‌ی کاربر با confidence=۲۰ و source="user"؛ هیچ‌وقت داده‌ی منبع‌دار رو بازنویسی نمی‌کنه.
  تأیید کاربر دومِ مستقل (عنوان هم‌خوان) اطمینان رو بالا می‌بره.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import isbn as isbn_lib
from .models import Book, Edition

USER_BASE_CONFIDENCE = 20
USER_CONFIRM_STEP = 15
USER_MAX_CONFIDENCE = 60
RETRY_USER_EDITION_AFTER = 7 * 24 * 3600     # ثانیه؛ هر هفته یه‌بار برای داده‌ی کاربری دوباره از منبع‌ها می‌پرسیم


def _from_merged(data):
    return {
        "title": data.get("title", "")[:300], "subtitle": data.get("subtitle", "")[:300], "authors": data.get("authors", []),
        "translators": data.get("translators", []), "publisher": data.get("publisher", "")[:200], "year": data.get("year"),
        "year_calendar": data.get("year_calendar", ""), "edition_no": data.get("edition_no", "")[:50], "volume": data.get("volume", "")[:50],
        "pages": data.get("pages"), "language": data.get("language", "")[:20], "subjects": data.get("subjects", []),
        "description": data.get("description", ""), "cover_url": data.get("cover_url", "")[:500],
    }


def _fetched_recently(edition):
    at = edition.provenance.get("fetched_at")
    return bool(at) and (timezone.now().timestamp() - at) < RETRY_USER_EDITION_AFTER


@transaction.atomic
def upsert_from_sources(isbn13, data):
    """نتیجه‌ی ادغام‌شده‌ی منبع‌ها ← Edition (می‌سازه یا داده‌ی کاربری قبلی رو با داده‌ی منبع‌دار جایگزین می‌کنه)."""
    edition = Edition.objects.select_for_update().filter(isbn13=isbn13).first() or Edition(isbn13=isbn13)
    users = edition.provenance.get("users", []) if edition.pk else []
    for field, value in _from_merged(data).items():
        setattr(edition, field, value)
    edition.source = "+".join(data["sources"])
    edition.confidence = data["confidence"]
    edition.provenance = {"fields": data["provenance"], "sources": data["sources"], "fetched_at": timezone.now().timestamp(), "users": users}
    try:
        with transaction.atomic():
            edition.save()
    except IntegrityError:               # دو درخواست هم‌زمان؛ برنده بالا ساخته شد
        edition = Edition.objects.get(isbn13=isbn13)
    return edition


def resolve(raw, fetch=True, timeout=None):
    """
    Edition برای یه شابک (هر قالبی)، یا None. بدون fetch فقط دیتابیس. با fetch: Edition منبع‌دار هیچ تماس شبکه‌ای نمی‌سازه،
    و Edition کاربری حداکثر هفته‌ای یه‌بار دوباره از منبع‌ها پرسیده می‌شه.
    """
    isbn13 = isbn_lib.normalize_isbn(raw)
    if not isbn13:
        return None
    edition = Edition.objects.filter(isbn13=isbn13).first()
    if edition and edition.is_source_backed:
        return edition
    if not fetch or (edition and _fetched_recently(edition)):
        return edition
    data = isbn_lib.lookup_full(isbn13, timeout)
    if data:
        return upsert_from_sources(isbn13, data)
    if edition:                                    # منبعی جواب نداد؛ زمان آخرین تلاش ثبت بشه تا هر درخواست دوباره نپرسه
        edition.provenance = {**edition.provenance, "fetched_at": timezone.now().timestamp()}
        Edition.objects.filter(pk=edition.pk).update(provenance=edition.provenance)
    return edition


@transaction.atomic
def record_user_entry(user, raw_isbn, title, author):
    """
    کاربر شابک+عنوان+نویسنده وارد کرده. Edition منبع‌دار دست‌نخورده می‌مونه. داده‌ی کاربری:
    - اگه نبود: ساخته می‌شه با confidence=۲۰؛ - اگه کاربر دیگه‌ای با عنوان هم‌خوان قبلاً ثبت کرده: اطمینان بالا می‌ره؛
    - عنوان ناهم‌خوان: چیزی عوض نمی‌شه (فقط تو provenance به‌عنوان تعارض ثبت می‌شه).
    """
    isbn13 = isbn_lib.normalize_isbn(raw_isbn)
    title = " ".join((title or "").split())
    if not isbn13 or not title:
        return None
    edition = Edition.objects.select_for_update().filter(isbn13=isbn13).first()
    if edition is None:
        try:
            with transaction.atomic():
                return Edition.objects.create(
                    isbn13=isbn13, title=title[:300], authors=[a for a in [" ".join((author or "").split())] if a], source=Edition.SOURCE_USER,
                    confidence=USER_BASE_CONFIDENCE, created_by=user, provenance={"users": [user.pk]})
        except IntegrityError:
            edition = Edition.objects.select_for_update().get(isbn13=isbn13)
    if edition.is_source_backed:
        return edition
    users = list(edition.provenance.get("users", []))
    if user.pk in users:
        return edition
    if isbn_lib.title_key(title) == isbn_lib.title_key(edition.title):
        users.append(user.pk)
        edition.confidence = min(USER_MAX_CONFIDENCE, USER_BASE_CONFIDENCE + USER_CONFIRM_STEP * (len(users) - 1))
        edition.provenance = {**edition.provenance, "users": users}
    else:
        conflicts = list(edition.provenance.get("conflicts", []))
        conflicts.append({"user": user.pk, "title": title[:200]})
        edition.provenance = {**edition.provenance, "conflicts": conflicts[-5:]}
    edition.save(update_fields=["confidence", "provenance", "updated_at"])
    return edition


def attach_edition(book):
    """Book جدید/ویرایش‌شده رو (فقط با دیتابیس، بدون شبکه) به Edition وصل می‌کنه و ISBN رو به ۱۳رقمی یکدست می‌کنه."""
    isbn13 = isbn_lib.normalize_isbn(book.isbn)
    if not isbn13:
        return None
    edition = Edition.objects.filter(isbn13=isbn13).first() or record_user_entry(book.owner, isbn13, book.title, book.author)
    updates = {}
    if book.isbn != isbn13:
        updates["isbn"] = isbn13
    if edition and book.edition_id != edition.pk:
        updates["edition"] = edition
    if updates:
        for k, v in updates.items():
            setattr(book, k, v)
        if book.pk:
            Book.all_objects.filter(pk=book.pk).update(**{("edition_id" if k == "edition" else k): (v.pk if k == "edition" else v) for k, v in updates.items()})
    return edition
