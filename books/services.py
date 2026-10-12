from notifications.services import notify

from .models import Wishlist


def notify_wishlists(book):
    """کسایی که عنوان، نویسنده یا شابکِ این کتاب تو لیست آرزوشونه خبردار می‌شن."""
    fields = [f.lower() for f in (book.title, book.author, book.isbn) if f]
    seen = set()
    for wish in Wishlist.objects.exclude(user=book.owner).select_related("user"):
        text = wish.text.strip().lower()
        if wish.user_id in seen or not text:
            continue
        if any(text in f or f in text for f in fields):
            seen.add(wish.user_id)
            notify(wish.user, f"کتابی که می‌خواستی ثبت شد: «{book.title}»", f"/books/{book.pk}/")
