from django.conf import settings

from .models import SiteSetting


def site(request):
    """تنظیمات سایت (متن فوتر، شبکه‌های اجتماعی، بنر) برای همه‌ی قالب‌ها."""
    ctx = {"site": SiteSetting.load(), "wishlist_enabled": settings.WISHLIST_ENABLED, "highlights_enabled": settings.HIGHLIGHTS_ENABLED,
           "porfam_url": settings.PORFAM_URL, "support_url": settings.SUPPORT_URL}
    user = getattr(request, "user", None)
    if user is not None and user.is_staff:
        from panel.utils import counts  # فقط برای مدیرها: تعداد موارد منتظر رسیدگی کنار «پنل مدیریت»

        ctx["staff_todo"] = sum(counts().values())
    return ctx
