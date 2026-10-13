"""عملیات حساب کاربری که روی تاریخچه‌ی دیگران اثر می‌ذارن."""

from django.db import transaction
from django.utils import timezone

from books.models import Book, Wishlist
from exchanges.models import Exchange


class AccountError(Exception):
    pass


@transaction.atomic
def anonymize_user(user):
    """
    «حذف حساب» = ناشناس‌سازی، نه حذف ردیف. مبادله‌ها، رأی‌ها و نقدهای طرف مقابل سالم می‌مونن.
    - نام کاربری می‌شه deleted_<id>؛ ایمیل و رمز پاک می‌شه؛ حساب غیرفعال می‌شه.
    - کتاب‌ها پنهان (حذف نرم) و معرفی‌ها به پیش‌نویس برمی‌گردن؛ لیست آرزو، اعلان‌ها و اشتراک‌های پوش پاک می‌شن.
    - هش شبکه‌ی ثبت‌نام عمداً می‌مونه تا حذف و ثبت‌نام دوباره سقف حساب هدیه‌ی هر شبکه رو دور نزنه.
    """
    if user.is_superuser:
        raise AccountError("حساب مدیر ارشد از اینجا حذف نمی‌شه.")
    if Exchange.objects.filter(status__in=Exchange.ACTIVE).filter(owner=user).exists() or Exchange.objects.filter(status__in=Exchange.ACTIVE, requester=user).exists():
        raise AccountError("تا مبادله‌های در جریانت تموم یا لغو نشدن نمی‌تونی حساب رو حذف کنی.")
    now = timezone.now()
    for book in Book.all_objects.filter(owner=user, deleted_at__isnull=True):
        book.soft_delete()
    user.posts.exclude(status="draft").update(status="draft")
    Wishlist.objects.filter(user=user).delete()
    # کتابخونه‌ی شخصی، دنبال‌کردن‌ها، هدف‌ها: داده‌ی شخصیه و با حذف حساب پاک می‌شه
    user.highlights.all().delete()
    user.reading_days.all().delete()
    user.shelf.all().delete()
    user.reading_goals.all().delete()
    user.following_set.all().delete()
    user.follower_set.all().delete()
    user.club_memberships.all().delete()
    user.club_posts.all().delete()
    user.club_votes.all().delete()
    user.club_proposals.all().delete()
    user.owned_clubs.update(is_active=False)
    user.notifications.all().delete()
    user.push_subscriptions.all().delete()
    user.announcement_bookmarks.all().delete()
    user.username = f"deleted_{user.pk}"
    user.first_name = user.last_name = user.email = user.display_name = ""
    user.last_ip_hash = ""
    user.set_unusable_password()
    user.is_active = False
    user.deleted_at = now
    user.save()
    return user
