"""
محدودیت نرخ ساده روی کش مشترک (جدول دیتابیس، تا بین worker های gunicorn هم کار کنه).
کلید: کاربر واردشده یا IP. سقف که پر شد ۴۲۹ برمی‌گرده.
"""

import functools
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def client_ip(request):
    """پشت nginx آی‌پی واقعی از X-Real-IP می‌آد (nginx خودش ست می‌کنه، کلاینت نمی‌تونه جعلش کنه)."""
    if settings.TRUST_PROXY_HEADERS:
        real = request.META.get("HTTP_X_REAL_IP")
        if real:
            return real.strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def hit(scope, ident, limit, window):
    """یه درخواست ثبت می‌کنه؛ اگه از سقف رد شد False برمی‌گردونه."""
    if not settings.THROTTLE_ENABLED:
        return True
    bucket = int(time.time() // window)
    key = f"thr:{scope}:{ident}:{bucket}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.add(key, 0, window * 2)
        count = cache.incr(key)
    return count <= limit


def _blocked(request, json):
    if json or request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"error": "rate_limited"}, status=429)
    resp = render(request, "429.html", status=429)
    resp["Retry-After"] = "60"
    return resp


def throttle(scope, limit, window, methods=("POST",), by="auto", json=False):
    """
    دکوراتور view. methods: فقط این متدها شمرده می‌شن (پیش‌فرض POST).
    by: 'user' | 'ip' | 'auto' (کاربر واردشده، وگرنه IP).
    """
    def deco(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method in methods:
                user = getattr(request, "user", None)
                use_user = by == "user" or (by == "auto" and user is not None and user.is_authenticated)
                ident = f"u{user.pk}" if use_user else f"ip{client_ip(request)}"
                if not hit(scope, ident, limit, window):
                    return _blocked(request, json)
            return view(request, *args, **kwargs)

        return wrapper

    return deco
