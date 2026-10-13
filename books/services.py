from django.conf import settings

from common.text import work_key
from notifications.services import notify as _notify

from .models import Book, Wishlist


def notify(user, text, url=""):
    return _notify(user, text, url, kind="wishlist")


def add_wish(user, text):
    """آرزو رو با اعتبارسنجی ثبت می‌کنه. (wish, None) یا (None, پیام خطا)."""
    from common.text import significant_words

    from .isbn import normalize as isbn_normalize

    text = " ".join((text or "").split())[:200]
    if not isbn_normalize(text) and not significant_words(text):
        return None, "حداقل یه کلمه‌ی مشخص (۳ حرف یا بیشتر؛ نه فقط «کتاب» یا «رمان») یا یه شابک بنویس."
    if user.wishes.count() >= Wishlist.MAX_PER_USER:
        return None, f"حداکثر {Wishlist.MAX_PER_USER} آرزو می‌تونی داشته باشی؛ چندتا رو پاک کن."
    wish, _ = Wishlist.objects.get_or_create(user=user, text=text)
    return wish, None


def matching_wishes(book):
    """
    آرزوهایی که این کتاب برآوردشون می‌کنه، بدون اسکن کل جدول:
    - شابک برابر (ایندکس isbn)، یا
    - همه‌ی کلمه‌های معنی‌دار آرزو، کلمه‌ی کامل (نه زیررشته) تو عنوان+نویسنده باشه؛ نامزدها از ایندکس WishToken.word.
    """
    from common.text import significant_words

    from .models import WishToken

    ids = set()
    if book.isbn:
        ids |= set(Wishlist.objects.filter(isbn=book.isbn).values_list("pk", flat=True))
    book_words = set(significant_words(f"{book.title} {book.author}"))
    if book_words:
        candidates = set(WishToken.objects.filter(word__in=book_words).values_list("wish_id", flat=True))
        if candidates:
            wanted = {}
            for wish_id, word in WishToken.objects.filter(wish_id__in=candidates).values_list("wish_id", "word"):
                wanted.setdefault(wish_id, set()).add(word)
            ids |= {wish_id for wish_id, ws in wanted.items() if ws <= book_words}
    return Wishlist.objects.filter(pk__in=ids).exclude(user=book.owner).select_related("user")


def notify_wishlists(book):
    """کسایی که کتابِ تازه آرزوشونه خبردار می‌شن؛ هر کاربر برای هر کتاب حداکثر یک اعلان."""
    if not settings.WISHLIST_ENABLED:
        return
    seen = set()
    for wish in matching_wishes(book):
        if wish.user_id in seen or not wish.user.is_active:
            continue
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
