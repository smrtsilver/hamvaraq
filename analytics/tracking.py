"""
شمارش بازدید یکتا و سخت‌گیرانه.

۱) صفحه‌ی HTML فقط برای بازدیدکننده‌ی عادی (نه ربات، نه مدیر، نه صاحب همون مورد) یه توکن امضاشده می‌ده.
۲) جاوااسکریپت صفحه بعد از چند ثانیه حضور واقعی (تب دیده‌شده + حداقل یه تعامل: اسکرول، لمس، حرکت ماوس، کلید) توکن رو برمی‌گردونه.
۳) سرور توکن رو چک می‌کنه (امضا، حداقل زمان حضور، حداکثر عمر)، و هر بازدیدکننده رو برای هر مورد فقط یک‌بار (برای همیشه) می‌شماره.
   بازدیدکننده‌ی عضو = شناسه‌ی کاربر؛ مهمان = هش یک‌طرفه‌ی (آی‌پی + مرورگر) تا پاک‌کردن کوکی بازدید جدید نسازه.
"""

import hashlib
import hmac
import re
import time

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from common.throttle import client_ip, hit

from .models import DailyVisitor, ViewLog

SALT = "hv-view"
MIN_DWELL = 3          # ثانیه؛ زودتر از این برگردونده بشه ربات‌ه
MAX_AGE = 60 * 60      # ثانیه؛ توکن قدیمی‌تر از یک ساعت بی‌اعتباره
BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|scrape|fetch|preview|headless|lighthouse|monitor|probe|check|curl|wget|python|httpclient|java|okhttp|go-http|"
    r"axios|node|libwww|facebookexternalhit|telegram|whatsapp|discord|twitter|pingdom|uptime|phantom|selenium|puppeteer|playwright",
    re.I,
)
SKIP_PREFIXES = ("/admin/", "/panel/", "/analytics/", "/static/", "/media/")


def user_agent(request):
    return request.META.get("HTTP_USER_AGENT", "")


def is_bot(request):
    ua = user_agent(request)
    if len(ua) < 20 or BOT_RE.search(ua):
        return True
    # پیش‌بارگذاری مرورگر یا پروکسی، بازدید واقعی نیست
    return request.META.get("HTTP_PURPOSE", "").lower() == "prefetch" or request.META.get("HTTP_SEC_PURPOSE", "").lower().startswith("prefetch")


def visitor_key(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"u{user.pk}"
    raw = f"{client_ip(request)}|{user_agent(request)}"
    return "g" + hmac.new(settings.SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()[:30]


def track(request, kind, obj, owner_id):
    """view صفحه‌ی جزئیات صدا می‌زنه تا بازدید این مورد (نه فقط سایت) دنبال بشه."""
    request._hv_view = (kind, obj.pk, owner_id or 0)


def issue_token(request):
    """توکن بازدید برای این صفحه، یا '' اگه شمردنی نیست."""
    user = getattr(request, "user", None)
    if request.method != "GET" or request.path.startswith(SKIP_PREFIXES) or is_bot(request):
        return ""
    if user is not None and user.is_authenticated and user.is_staff:
        return ""
    kind, obj_id, owner_id = getattr(request, "_hv_view", ("site", 0, 0))
    if user is not None and user.is_authenticated and owner_id and user.pk == owner_id:
        kind, obj_id, owner_id = "site", 0, 0     # صاحب مورد: فقط حضور در سایت، نه بازدید مورد خودش
    return signing.dumps({"k": kind, "i": obj_id, "o": owner_id, "t": int(time.time())}, salt=SALT, compress=True)


def _bump(model, pk):
    model.objects.filter(pk=pk).update(view_count=F("view_count") + 1)


def record(request, token):
    """بازدید رو (اگه معتبر و یکتا بود) ثبت می‌کنه. True فقط وقتی چیزی تازه شمرده شد."""
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
        kind, obj_id, owner_id, issued = data["k"], int(data["i"]), int(data["o"]), int(data["t"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return False
    user = getattr(request, "user", None)
    member = user is not None and user.is_authenticated
    if time.time() - issued < MIN_DWELL or is_bot(request) or (member and user.is_staff):
        return False
    if member and owner_id and user.pk == owner_id:
        return False
    visitor = visitor_key(request)
    if not hit("view", visitor, 90, 60):      # کسی که تو یک دقیقه ده‌ها مورد می‌بینه اسکریپته
        return False
    counted = False
    try:
        with transaction.atomic():
            _, created = DailyVisitor.objects.get_or_create(day=timezone.localdate(), visitor=visitor, defaults={"is_member": member})
        counted = created
    except IntegrityError:
        pass
    if kind != "site":
        model = _model(kind)
        if model is None or not model.objects.filter(pk=obj_id).exists():
            return counted
        try:
            with transaction.atomic():
                ViewLog.objects.create(kind=kind, object_id=obj_id, visitor=visitor, is_member=member)
            _bump(model, obj_id)
            counted = True
        except IntegrityError:
            pass      # قبلاً شمرده شده
    return counted


def _model(kind):
    from announcements.models import Announcement
    from books.models import Book
    from posts.models import Post

    return {"book": Book, "post": Post, "event": Announcement}.get(kind)
