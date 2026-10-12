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
    new += _challenge_badges(user)
    return new


def _challenge_badges(user):
    """چالشی که کاربر تو بازه‌اش به هدف رسیده نشان مخصوص خودش رو می‌گیره."""
    from django.utils import timezone

    from challenges.models import Challenge
    from notifications.services import notify

    now = timezone.now()
    new = []
    for c in Challenge.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now):
        if c.target and c.progress(user) >= c.target:
            badge, _ = Badge.objects.get_or_create(
                code=c.badge_code, defaults={"name": f"چالش: {c.title}", "description": c.description or c.title})
            _, created = UserBadge.objects.get_or_create(user=user, badge=badge)
            if created:
                new.append(badge)
                notify(user, f"چالش «{c.title}» رو کامل کردی و نشانش رو گرفتی!", "/challenges/")
    return new


def grant_welcome(user, key):
    """
    امتیاز خوش‌آمد: هر کاربر جدید WELCOME_POINTS می‌گیره تا بتونه فوراً کتاب بگیره.
    هر شبکه (آی‌پی) تو WELCOME_WINDOW_DAYS روز فقط به WELCOME_MAX_PER_IP حساب هدیه می‌ده؛
    مبادله خودش امتیاز نمی‌سازه، پس این تنها جاییه که امتیاز «ساخته» می‌شه و فقط همین‌جا کنترل می‌خوایم.
    برمی‌گردونه: امتیازی که داده شد (۰ اگه سقف شبکه پر بود).
    """
    from datetime import timedelta

    from django.utils import timezone

    from .models import User

    if settings.WELCOME_POINTS <= 0:
        return 0
    if key:
        since = timezone.now() - timedelta(days=settings.WELCOME_WINDOW_DAYS)
        used = User.objects.filter(signup_ip_hash=key, welcome_granted=True, date_joined__gte=since).exclude(pk=user.pk).count()
        if used >= settings.WELCOME_MAX_PER_IP:
            return 0
    user.points += settings.WELCOME_POINTS
    user.welcome_granted = True
    user.save(update_fields=["points", "welcome_granted"])
    return settings.WELCOME_POINTS
