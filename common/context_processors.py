from django.conf import settings

from .models import SiteSetting


def site(request):
    """تنظیمات سایت (متن فوتر، شبکه‌های اجتماعی، بنر) برای همه‌ی قالب‌ها."""
    ctx = {"site": SiteSetting.load(), "wishlist_enabled": settings.WISHLIST_ENABLED, "highlights_enabled": settings.HIGHLIGHTS_ENABLED,
           "porfam_url": settings.PORFAM_URL, "support_url": settings.SUPPORT_URL}
    ctx["back_url"] = back_url(request)
    user = getattr(request, "user", None)
    if user is not None and user.is_staff:
        from panel.utils import counts  # فقط برای مدیرها: تعداد موارد منتظر رسیدگی کنار «پنل مدیریت»

        ctx["staff_todo"] = sum(counts().values())
    return ctx


TOP_LEVEL = {":home", ":landing", "books:list", "exchanges:list", "panel:index"}
PARENT = {"books:detail": "books:list", "books:edit": "books:mine", "books:relist": "books:mine", "books:bulk": "books:mine",
          "books:shelf_add": "books:shelf", "books:shelf_edit": "books:shelf", "books:shelf_stats": "books:shelf",
          "exchanges:detail": "exchanges:list", "posts:detail": "posts:list", "announcements:detail": "announcements:list",
          "clubs:detail": "clubs:list", "notifications:settings": "notifications:list", "city": "cities", "province": "cities"}
NS_HOME = {"panel": "panel:index", "posts": "posts:list", "announcements": "announcements:list", "clubs": "clubs:list",
           "challenges": "challenges:list", "accounts": "accounts:settings", "support": "accounts:settings", "trust": "home"}


def back_url(request):
    """آدرس «بازگشت» هدر؛ None یعنی صفحه‌ی سطح اول (دکمه نشون داده نمی‌شه). مرورگر اول history.back رو امتحان می‌کنه."""
    from django.urls import NoReverseMatch, reverse

    m = getattr(request, "resolver_match", None)
    if m is None:
        return None
    key = f"{m.namespace}:{m.url_name}" if m.namespace else m.url_name
    if f":{key}" in TOP_LEVEL or key in TOP_LEVEL:
        return None
    user = getattr(request, "user", None)
    if key == "accounts:profile" and user is not None and user.is_authenticated and m.kwargs.get("username") == user.username:
        return None
    target = PARENT.get(key) or NS_HOME.get(m.namespace) or "home"
    if target == key:
        target = "home"
    try:
        return reverse(target)
    except NoReverseMatch:
        return reverse("home")
