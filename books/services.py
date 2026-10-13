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


def matching_wishes_for(isbn, title, author, exclude_user=None):
    """
    آرزوهایی که این کتاب برآوردشون می‌کنه، بدون اسکن کل جدول:
    - شابک برابر (ایندکس isbn)، یا
    - همه‌ی کلمه‌های معنی‌دار آرزو، کلمه‌ی کامل (نه زیررشته) تو عنوان+نویسنده باشه؛ نامزدها از ایندکس WishToken.word.
    """
    from common.text import significant_words

    from .models import WishToken

    ids = set()
    if isbn:
        ids |= set(Wishlist.objects.filter(isbn=isbn).values_list("pk", flat=True))
    book_words = set(significant_words(f"{title} {author}"))
    if book_words:
        candidates = set(WishToken.objects.filter(word__in=book_words).values_list("wish_id", flat=True))
        if candidates:
            wanted = {}
            for wish_id, word in WishToken.objects.filter(wish_id__in=candidates).values_list("wish_id", "word"):
                wanted.setdefault(wish_id, set()).add(word)
            ids |= {wish_id for wish_id, ws in wanted.items() if ws <= book_words}
    qs = Wishlist.objects.filter(pk__in=ids).select_related("user")
    return qs.exclude(user=exclude_user) if exclude_user is not None else qs


def matching_wishes(book):
    return matching_wishes_for(book.isbn, book.title, book.author, exclude_user=book.owner)


def demand_for(isbn, title, author, exclude_user=None, days=90):
    """«چند نفر دنبال این کتابن»: آرزوهای هم‌خوان + درخواست‌دهنده‌های متفاوتِ نسخه‌های همین کتاب تو چند ماه اخیر."""
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from exchanges.models import Exchange

    wishers = set(matching_wishes_for(isbn, title, author, exclude_user).values_list("user_id", flat=True)) if settings.WISHLIST_ENABLED else set()
    cond = Q(book__work_key=work_key(title, author))
    if isbn:
        cond |= Q(book__isbn=isbn)
    since = timezone.now() - timedelta(days=days)
    requesters = set(Exchange.objects.filter(cond, created_at__gte=since).values_list("requester_id", flat=True))
    if exclude_user is not None:
        requesters.discard(exclude_user.pk)
        wishers.discard(exclude_user.pk)
    return len(wishers | requesters)


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
