"""اعطای نشان‌ها. هر نشان با یه شرط ساده از روی داده‌های موجود محاسبه می‌شه."""

from django.conf import settings

from .models import Badge, UserBadge

DEFINITIONS = {
    "book-lover": ("کتاب‌دوست", "اولین مبادله‌ی کامل‌شده"),
    "courier": ("پیک کتاب", "چند مبادله‌ی کامل‌شده"),
    "neighborhood-library": ("کتابخونه‌ی محله", "چند کتاب هم‌زمان در قفسه"),
}


def _award(user, code):
    name, description = DEFINITIONS[code]
    badge, _ = Badge.objects.get_or_create(code=code, defaults={"name": name, "description": description})
    _, created = UserBadge.objects.get_or_create(user=user, badge=badge)
    return badge if created else None


def check_badges(user):
    """بعد از هر رویداد مهم صدا زده می‌شه؛ نشان‌های تازه رو برمی‌گردونه و اعلان می‌ده."""
    from books.models import Book
    from exchanges.models import Exchange
    from notifications.services import notify

    done = Exchange.objects.filter(status=Exchange.Status.COMPLETED).filter(
        owner=user
    ).count() + Exchange.objects.filter(status=Exchange.Status.COMPLETED, requester=user).count()
    shelf = Book.objects.filter(owner=user, status=Book.Status.AVAILABLE).count()

    earned = []
    if done >= 1:
        earned.append("book-lover")
    if done >= settings.BADGE_COURIER_EXCHANGES:
        earned.append("courier")
    if shelf >= settings.BADGE_NEIGHBORHOOD_BOOKS:
        earned.append("neighborhood-library")

    new = []
    for code in earned:
        badge = _award(user, code)
        if badge:
            new.append(badge)
            notify(user, f"نشان «{badge.name}» رو گرفتی!", f"/accounts/u/{user.username}/")
    return new
