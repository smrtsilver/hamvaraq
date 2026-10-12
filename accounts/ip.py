"""شناسه‌ی شبکه‌ی کاربر برای کنترل سوءاستفاده. آی‌پی خام ذخیره نمی‌شه؛ فقط HMAC یک‌طرفه‌ی اون."""

import hashlib
import hmac
import ipaddress

from django.conf import settings

from common.throttle import client_ip


def ip_key(request):
    """
    هش آی‌پی کاربر، یا '' اگه آی‌پی خصوصی/لوکال باشه (توسعه، یا پروکسی بد تنظیم‌شده).
    خالی یعنی «نمی‌شه شمرد»؛ این‌جا عمداً به نفع کاربر عمل می‌کنیم تا خطای تنظیمات کسی رو قفل نکنه.
    آی‌پی ۶ با /64 گروه می‌شه چون هر کاربر عملاً کل اون بازه رو داره.
    """
    try:
        addr = ipaddress.ip_address(client_ip(request))
    except ValueError:
        return ""
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_unspecified:
        return ""
    if addr.version == 6:
        addr = ipaddress.ip_network(f"{addr}/64", strict=False).network_address
    return hmac.new(settings.SECRET_KEY.encode(), str(addr).encode(), hashlib.sha256).hexdigest()
