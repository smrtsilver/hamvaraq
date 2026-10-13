"""جستجوی شابک: اول کتاب‌های خود هم‌ورق (هر شابکی که یکی ثبت کرده باشه برای بعدی خودکار پر می‌شه)،
بعد شبکه‌ی کتابخانه‌های کشور (libs.nlai.ir، کتابخانه‌ی ملی؛ کتاب فارسی داره)،
بعد Open Library، بعد Google Books. کتاب‌های فارسی همیشه تو منبع‌های بیرونی نیستن؛ نتیجه‌ی خالی عادیه."""

import json
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
GOOGLE_API = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1"
NLAI = "https://libs.nlai.ir"
NLAI_SEARCH = NLAI + "/search?{qs}"
NLAI_MARC = NLAI + "/get/marc?{qs}"
NLAI_HEADERS = {"User-Agent": "Mozilla/5.0 (HamVaraq ISBN lookup)"}
NLAI_MAX_CANDIDATES = 5


def normalize(raw):
    """شابک ۱۰ یا ۱۳ رقمی (با خط تیره و فاصله) ← رقم‌های خالص، یا None."""
    isbn = re.sub(r"[\s-]", "", (raw or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))).upper()
    if re.fullmatch(r"\d{13}", isbn) or re.fullmatch(r"\d{9}[\dX]", isbn):
        return isbn
    return None


def _fetch(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


_BIDI = re.compile("[‎‏‪-‮⁦-⁩]")


def _clean(text):
    return re.sub(r"\s+", " ", _BIDI.sub("", text or "")).strip(" 	،,:/؛;.")


def parse_marc(data):
    """رکوردهای ISO2709 ← لیستی از {تگ: [[(کد, مقدار), ...] یا متنِ فیلد‌های کنترلی]}."""
    records = []
    for raw in data.split(b"\x1d"):
        if len(raw) < 25 or not raw[12:17].isdigit():
            continue
        base = int(raw[12:17])
        fields = {}
        for i in range(24, base - 1, 12):
            entry = raw[i : i + 12]
            if len(entry) < 12 or not entry[3:12].isdigit():
                break
            tag, length, start = entry[:3].decode("ascii", "replace"), int(entry[3:7]), int(entry[7:12])
            body = raw[base + start : base + start + length].rstrip(b"\x1e").decode("utf-8", "replace")
            subs = [(p[0], p[1:]) for p in body.split("\x1f")[1:] if p]
            fields.setdefault(tag, []).append(subs if subs else body)
        records.append(fields)
    return records


def _sub(fields, tag, code):
    for field in fields.get(tag, []):
        if isinstance(field, list):
            for c, value in field:
                if c == code:
                    return value
    return ""


def _from_marc(fields, isbn):
    """رکورد UNIMARC ← {'isbn','title','author'}؛ None اگه شابکش با شابک پرسیده‌شده نخونه."""
    if normalize(_clean(_sub(fields, "010", "a"))) != isbn:
        return None
    title = _clean(_sub(fields, "200", "a"))
    if not title:
        return None
    subtitle = _clean(_sub(fields, "200", "e"))
    if subtitle:
        title = f"{title}: {subtitle}"
    author = ""
    for tag in ("700", "701", "702"):
        family, given = _clean(_sub(fields, tag, "a")), _clean(_sub(fields, tag, "b"))
        author = f"{given} {family}".strip()
        if author:
            break
    return {"isbn": isbn, "title": title, "author": author}


def _get(url, timeout):
    req = urllib.request.Request(url, headers=NLAI_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _nlai(isbn, timeout):
    """دو درخواست پشت هم (جستجو ← رکورد MARC)؛ جمعشون از بودجه‌ی timeout بیشتر نمی‌شه."""
    deadline = time.monotonic() + timeout

    def left():
        return max(0.3, deadline - time.monotonic())

    page = _get(NLAI_SEARCH.format(qs=urllib.parse.urlencode({"query": isbn})), left()).decode("utf-8", "replace")
    uids = list(dict.fromkeys(re.findall(r"/bibliography/([\w-]+)/", page)))[:NLAI_MAX_CANDIDATES]
    if not uids:
        return None
    qs = urllib.parse.urlencode([("uid", u) for u in uids])
    for fields in parse_marc(_get(NLAI_MARC.format(qs=qs), left())):
        result = _from_marc(fields, isbn)
        if result:
            return result
    return None


def _local(isbn):
    from .models import Book
    book = Book.objects.filter(isbn=isbn).exclude(title="").order_by("-created_at").first()
    return {"isbn": isbn, "title": book.title, "author": book.author} if book else None


def _open_library(isbn, timeout):
    info = _fetch(API.format(isbn=isbn), timeout).get(f"ISBN:{isbn}")
    if info and info.get("title"):
        authors = ", ".join(a.get("name", "") for a in info.get("authors", []) if a.get("name"))
        return {"isbn": isbn, "title": info["title"], "author": authors}


def _google(isbn, timeout):
    url = GOOGLE_API.format(isbn=isbn)
    key = getattr(settings, "GOOGLE_BOOKS_API_KEY", "")
    if key:
        url += f"&key={key}"
    items = _fetch(url, timeout).get("items") or []
    info = items[0].get("volumeInfo", {}) if items else {}
    if info.get("title"):
        return {"isbn": isbn, "title": info["title"], "author": ", ".join(info.get("authors") or [])}


# ترتیب = اولویت منبع‌ها (کتابخانه‌ی ملی برای کتاب فارسی بهتره)
SOURCE_NAMES = ("nlai", "openlibrary", "google")
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="isbn")
_BREAKER_LOCK = threading.Lock()


def _budget():
    return float(getattr(settings, "ISBN_BUDGET", 3.0))


def breaker_open(name):
    """منبعی که پشت‌سرهم خراب بوده چند دقیقه کنار می‌ره تا هر درخواست منتظرش نمونه."""
    state = cache.get(f"isbn:cb:{name}") or {}
    return state.get("until", 0) > time.time()


def breaker_record(name, ok):
    key = f"isbn:cb:{name}"
    with _BREAKER_LOCK:
        if ok:
            cache.delete(key)
            return
        state = cache.get(key) or {"fails": 0}
        state["fails"] = state.get("fails", 0) + 1
        if state["fails"] >= getattr(settings, "ISBN_BREAKER_FAILS", 3):
            state = {"fails": 0, "until": time.time() + getattr(settings, "ISBN_BREAKER_COOLDOWN", 300)}
        cache.set(key, state, 3600)


def lookup(raw, timeout=None):
    """
    {'isbn','title','author'} یا None. منبع‌ها هم‌زمان و با بودجه‌ی زمانی کل (پیش‌فرض ۳ ثانیه) پرسیده می‌شن،
    پس یه منبع کند هیچ‌وقت درخواست رو بیشتر از بودجه نگه نمی‌داره. نتیجه‌ی منفیِ ناشی از خطا/timeout کش نمی‌شه.
    همه‌ی کار کش/دیتابیس تو همین thread انجام می‌شه؛ thread‌های شبکه فقط urllib صدا می‌زنن.
    """
    isbn = normalize(raw)
    if not isbn:
        return None
    result = _local(isbn)
    if result:
        return result
    key = f"isbn:{isbn}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    budget = float(timeout) if timeout else _budget()
    deadline = time.monotonic() + budget
    funcs = {"nlai": _nlai, "openlibrary": _open_library, "google": _google}     # موقع صدا زدن خونده می‌شن (تست‌ها می‌تونن جایگزین کنن)
    order = list(SOURCE_NAMES)
    pending = {name: _POOL.submit(funcs[name], isbn, budget) for name in order if not breaker_open(name)}
    results, failed = {}, len(pending) < len(order)    # منبع کنار گذاشته‌شده = جواب ناقص ⇒ منفی کش نشه
    found = None
    while pending and found is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        done, _ = wait(list(pending.values()), timeout=remaining, return_when=FIRST_COMPLETED)
        for name, fut in list(pending.items()):
            if fut in done:
                del pending[name]
                try:
                    results[name] = fut.result()
                    breaker_record(name, True)
                except Exception:        # خطای شبکه، تجزیه، هر چیزی؛ منبع خراب نباید سایت رو بزنه
                    results[name] = None
                    failed = True
                    breaker_record(name, False)
        for name in order:               # بالاترین منبعِ تمام‌شده‌ای که جواب داره، مگه منبعِ مهم‌تری هنوز تو راه باشه
            if name in pending:
                break
            if results.get(name):
                found = results[name]
                break
    for name in pending:                 # بودجه تموم شد: منابع معطل شکست حساب می‌شن (thread‌شون خودش با timeout تموم می‌شه)
        failed = True
        breaker_record(name, False)
    if found is None:
        found = next((results[n] for n in order if results.get(n)), None)
    if found or not failed:
        cache.set(key, found or {}, 60 * 60 * 24)
    return found
