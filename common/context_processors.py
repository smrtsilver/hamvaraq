from .models import SiteSetting


def site(request):
    """تنظیمات سایت (متن فوتر، شبکه‌های اجتماعی، بنر) برای همه‌ی قالب‌ها."""
    return {"site": SiteSetting.load()}
