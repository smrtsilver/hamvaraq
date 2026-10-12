from django.conf import settings

from common.text import normalize, work_key
from notifications.services import notify as _notify

from .models import Book, Wishlist


def notify(user, text, url=""):
    return _notify(user, text, url, kind="wishlist")


def notify_wishlists(book):
    """کسایی که عنوان، نویسنده یا شابکِ این کتاب تو لیست آرزوشونه خبردار می‌شن."""
    if not settings.WISHLIST_ENABLED:
        return
    fields = [normalize(f) for f in (book.title, book.author, book.isbn) if f]
    seen = set()
    for wish in Wishlist.objects.exclude(user=book.owner).select_related("user"):
        text = normalize(wish.text)
        if wish.user_id in seen or not text:
            continue
        if any(text in f or f in text for f in fields):
            seen.add(wish.user_id)
            notify(wish.user, f"کتابی که می‌خواستی ثبت شد: «{book.title}»", f"/books/{book.pk}/")


def same_work(book):
    """نسخه‌های دیگه‌ی همین کتاب: شابک یکسان، وگرنه عنوان و نویسنده‌ی یکسان."""
    from django.db.models import Q

    q = Q(work_key=book.work_key or work_key(book.title, book.author))
    if book.isbn:
        q |= Q(isbn=book.isbn)
    return Book.objects.filter(q)


def similar_books(book, limit=6):
    """
    «هم‌سلیقه‌ها»: کتاب‌های موجودِ کسایی که این کتاب (یا نسخه‌ی دیگه‌ش) رو داشتن، دادن یا گرفتن.
    اگه کم بود، با کتاب‌های هم‌دسته پر می‌شه.
    """
    from exchanges.models import Exchange

    copies = same_work(book)
    people = set(copies.values_list("owner_id", flat=True))
    done = Exchange.objects.filter(book__in=copies, status=Exchange.Status.COMPLETED)
    people.update(done.values_list("owner_id", flat=True))
    people.update(done.values_list("requester_id", flat=True))

    base = Book.objects.filter(status=Book.Status.AVAILABLE).exclude(pk__in=copies.values("pk")).select_related("city")
    result = list(base.filter(owner_id__in=people).order_by("-created_at")[:limit])
    if len(result) < limit and book.category_id:
        taken = [b.pk for b in result]
        result += list(base.filter(category_id=book.category_id).exclude(pk__in=taken).order_by("-created_at")[: limit - len(result)])
    return result
