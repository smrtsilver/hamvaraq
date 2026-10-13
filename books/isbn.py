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


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def clean_digits(raw):
    """رقم فارسی/عربی ← انگلیسی؛ فاصله، خط‌تیره و نویسه‌های جهت‌نما حذف؛ X بزرگ."""
    text = _BIDI.sub("", (raw or "").translate(_DIGITS))
    return re.sub(r"[\s\-‐-―_.]", "", text).upper()


def isbn10_valid(d):
    return bool(re.fullmatch(r"\d{9}[\dX]", d)) and sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d)) % 11 == 0


def isbn13_valid(d):
    return bool(re.fullmatch(r"\d{13}", d)) and sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d)) % 10 == 0


def isbn10_to_13(d):
    body = "978" + d[:9]
    return body + str((10 - sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(body)) % 10) % 10)


def normalize_isbn(raw):
    """
    هر شابک ۱۰ یا ۱۳ رقمی (با رقم فارسی، خط‌تیره و فاصله) ← ISBN-13 خالص؛ اگه رقم کنترل غلط بود None.
    ISBN-10 و ISBN-13 یه کتاب هر دو به یه مقدار می‌رسن.
    """
    d = clean_digits(raw)
    if isbn13_valid(d):
        return d
    if isbn10_valid(d):
        return isbn10_to_13(d)
    return None


normalize = normalize_isbn      # نام قدیمی؛ فرم‌ها و تست‌ها هنوز ازش استفاده می‌کنن


def isbn_error(raw):
    """پیام خطای فارسی برای ورودی نامعتبر یا None اگه معتبره (یا خالیه)."""
    d = clean_digits(raw)
    if not d:
        return None
    if normalize_isbn(d):
        return None
    if re.fullmatch(r"\d{10}|\d{9}X|\d{13}", d):
        return "رقم کنترل این شابک درست نیست؛ یه بار دیگه چک کن."
    return "شابک باید ۱۰ یا ۱۳ رقم باشه."


# کنترل‌های جهت + «اتصال» (ZWJ) که کتابخانه‌ی ملی وسط حروف نام‌ها می‌ذاره (م‍ن‍ی‍ژه)؛ نیم‌فاصله (ZWNJ) می‌مونه
_BIDI = re.compile("[‍‎‏‪-‮⁦-⁩]")


def _fetch(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def _clean(text):
    text = re.sub(r"‌+(?=\s|$)|(?<=\s)‌+|^‌+", "", _BIDI.sub("", text or ""))   # نیم‌فاصله‌ی سرِ کلمه بی‌معنیه
    return re.sub(r"\s+", " ", text).strip(" 	،,:/؛;.")


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


def _year_info(raw):
    """«۱۳۹۲» یا «c2001» ← (سال عددی, 'jalali'|'gregorian'). سال‌های کمتر از ۱۷۰۰ شمسی حساب می‌شن."""
    m = re.search(r"\d{4}", clean_digits(raw))
    if not m:
        return None, ""
    year = int(m.group())
    return year, ("jalali" if year < 1700 else "gregorian")


def _int(raw):
    m = re.search(r"\d+", clean_digits(raw))
    return int(m.group()) if m else None


def _person(fields, tag):
    """همه‌ی فیلدهای شخص (700/701/702) ← [(نام کامل, نقش $4, کد خط $7)]."""
    out = []
    for field in fields.get(tag, []):
        if not isinstance(field, list):
            continue
        family = given = role = script = ""
        for code, value in field:
            if code == "a" and not family:
                family = _clean(value)
            elif code == "b" and not given:
                given = _clean(value)
            elif code == "4" and not role:
                role = _clean(value)
            elif code == "7" and not script:
                script = value.strip()
        name = f"{given} {family}".strip()
        if name:
            out.append((name, role, script))
    return out


TRANSLATOR_ROLES = {"730"}
# نقش‌های غیرِ نویسنده (ویراستار، تصویرگر، مقدمه‌نویس…) نه نویسنده‌ان نه مترجم؛ کنار گذاشته می‌شن
OTHER_ROLE_WORDS = ("ویراست", "تصویرگر", "مصور", "مقدمه", "زیر نظر", "طراح", "عکاس", "خوانش", "گوینده", "صفحه", "ناظر")
_PERSIAN = re.compile("[؀-ۿ]")


def _role_kind(role):
    """«author» | «translator» | None (نقش دیگه). نقش خالی یعنی پدیدآور اصلی."""
    r = (role or "").replace("‌", "")
    if r in TRANSLATOR_ROLES or "ترجم" in r:
        return "translator"
    if any(w.replace("‌", "") in r for w in OTHER_ROLE_WORDS):
        return None
    return "author"


def _drop_latin_twins(names):
    """کتابخانه‌ی ملی کنار نام فارسی، همون نام رو با حروف لاتین هم ثبت می‌کنه؛ وقتی نسخه‌ی فارسی هست لاتین حذف می‌شه."""
    if any(_PERSIAN.search(n) for n in names):
        return [n for n in names if _PERSIAN.search(n)]
    return names


def _from_marc(fields, isbn):
    """رکورد UNIMARC ← دیکشنری غنی؛ None اگه شابکش با شابک پرسیده‌شده نخونه (شابک ۱۰ و ۱۳ یکی حساب می‌شن)."""
    if normalize_isbn(_clean(_sub(fields, "010", "a"))) != isbn:
        return None
    return _marc_record(fields, isbn)


def _marc_record(fields, isbn):
    """رکورد UNIMARC ← دیکشنری غنی (بدون شرط تطابق شابک)؛ None اگه عنوان نداشت."""
    title = _clean(_sub(fields, "200", "a"))
    if not title:
        return None
    authors, translators = [], []
    for tag in ("700", "701", "702"):
        for name, role, _script in _person(fields, tag):
            kind = _role_kind(role)
            target = translators if kind == "translator" else authors if kind == "author" else None
            if target is not None and name not in target:
                target.append(name)
    authors, translators = _drop_latin_twins(authors), _drop_latin_twins(translators)
    year, calendar = _year_info(_sub(fields, "210", "d"))
    record = {
        "isbn": isbn, "title": title, "subtitle": _clean(_sub(fields, "200", "e")),
        "authors": authors, "translators": translators,
        "publisher": _clean(_sub(fields, "210", "c")), "year": year, "year_calendar": calendar,
        "edition_no": _clean(_sub(fields, "205", "a")), "volume": _clean(_sub(fields, "200", "h")),
        "pages": _int(_sub(fields, "215", "a")), "language": _clean(_sub(fields, "101", "a")),
        "subjects": [x for x in dict.fromkeys(_clean(v) for f in fields.get("606", []) if isinstance(f, list) for c, v in f if c == "a") if x][:8],
        "description": _clean(_sub(fields, "330", "a")),
    }
    return {k: v for k, v in record.items() if v not in ("", None, [])}


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


NLAI_TITLE_LIMIT = 6
NLAI_TITLE_CANDIDATES = 12
NLAI_TITLE_CACHE = 6 * 3600


def nlai_title_search(query, timeout=None, limit=NLAI_TITLE_LIMIT):
    """
    جستجوی عنوان/نویسنده در کتابخانه‌ی ملی ← فهرست رکوردهای کامل (عنوان، پدیدآور، ناشر، سال، شابک…).
    برای وقتی که شابک تو هیچ منبعی نیست (مثلاً چاپ تازه)؛ کاربر چاپ درست رو انتخاب می‌کنه. نتیجه ۶ ساعت کش می‌شه.
    """
    import hashlib

    from common.text import normalize as text_normalize

    q = " ".join((query or "").split())[:120]
    if len(q) < 3:
        return []
    key = "nlai:title:" + hashlib.sha1(text_normalize(q).encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    deadline = time.monotonic() + (timeout or getattr(settings, "ISBN_BUDGET", 3.0) + 7)   # کاربر خودش «بگرد» رو زده؛ صبر بیشتری داریم

    def left():
        return max(0.3, deadline - time.monotonic())

    page = _get(NLAI_SEARCH.format(qs=urllib.parse.urlencode({"query": q})), left()).decode("utf-8", "replace")
    uids = list(dict.fromkeys(re.findall(r"/bibliography/([\w-]+)/", page)))[:NLAI_TITLE_CANDIDATES]
    records = []
    if uids:
        for fields in parse_marc(_get(NLAI_MARC.format(qs=urllib.parse.urlencode([("uid", u) for u in uids])), left())):
            raw = _clean(_sub(fields, "010", "a"))
            record = _marc_record(fields, (normalize_isbn(raw) if raw else None) or "")
            if record:
                records.append(record)
    # ترتیب خود کتابخانه‌ی ملی به شباهت عنوان اهمیت نمی‌ده؛ نزدیک‌ترین عنوان/نویسنده به عبارت جستجو بالا میاد
    want = text_normalize(q)
    want_words = set(want.split())

    def score(rec):
        title = text_normalize(f"{rec.get('title', '')} {rec.get('subtitle', '')}")
        people = text_normalize(" ".join(rec.get("authors", []) + rec.get("translators", [])))
        words_hit = len(want_words & set(f"{title} {people}".split())) / max(1, len(want_words))
        return (want == text_normalize(rec.get("title", "")),      # عنوان دقیقاً همین
                title.startswith(want),                          # با همین شروع می‌شه
                want in title or want in people,                 # جایی تو عنوان یا نام پدیدآور
                round(words_hit, 2), bool(rec.get("isbn")))      # هم‌پوشانی کلمه‌ها؛ رکورد شابک‌دار جلوتر

    out = sorted(records, key=score, reverse=True)[:limit]
    cache.set(key, out, NLAI_TITLE_CACHE)
    return out


def _compact(record):
    return {k: v for k, v in record.items() if v not in ("", None, [])}


def _opac(isbn, timeout):
    """فهرستگان کتابخانه‌ی ملی (فیپای کتاب‌های تازه)؛ books/iran_isbn.py"""
    from . import iran_isbn

    return iran_isbn.opac(isbn, timeout)


def _ketab(isbn, timeout):
    """خانه‌ی کتاب (مرجع صدور شابک ایران)؛ books/iran_isbn.py"""
    from . import iran_isbn

    return iran_isbn.ketab(isbn, timeout)


def _open_library(isbn, timeout):
    info = _fetch(API.format(isbn=isbn), timeout).get(f"ISBN:{isbn}")
    if not (info and info.get("title")):
        return None
    year, calendar = _year_info(info.get("publish_date", ""))
    cover = info.get("cover") or {}
    return _compact({
        "isbn": isbn, "title": info["title"], "subtitle": info.get("subtitle", ""),
        "authors": [a["name"] for a in info.get("authors", []) if a.get("name")],
        "publisher": ", ".join(p["name"] for p in info.get("publishers", []) if p.get("name")),
        "year": year, "year_calendar": calendar, "pages": info.get("number_of_pages"),
        "subjects": [x["name"] for x in info.get("subjects", []) if x.get("name")][:8],
        "cover_url": cover.get("large") or cover.get("medium") or "",
    })


def _google(isbn, timeout):
    url = GOOGLE_API.format(isbn=isbn)
    key = getattr(settings, "GOOGLE_BOOKS_API_KEY", "")
    if key:
        url += f"&key={key}"
    items = _fetch(url, timeout).get("items") or []
    info = items[0].get("volumeInfo", {}) if items else {}
    if not info.get("title"):
        return None
    year, calendar = _year_info(info.get("publishedDate", ""))
    cover = (info.get("imageLinks") or {}).get("thumbnail", "").replace("http://", "https://")
    return _compact({
        "isbn": isbn, "title": info["title"], "subtitle": info.get("subtitle", ""), "authors": info.get("authors") or [],
        "publisher": info.get("publisher", ""), "year": year, "year_calendar": calendar, "pages": info.get("pageCount"),
        "language": info.get("language", ""), "subjects": (info.get("categories") or [])[:8],
        "description": info.get("description", ""), "cover_url": cover,
    })


# ---------------------------------------------------------------- ادغام و اطمینان
# ترتیب = اولویت ادغام (کتاب فارسی: منبع‌های ایرانی بهترن). کدوم‌ها واقعاً پرسیده بشن از settings.ISBN_SOURCES میاد
SOURCE_NAMES = ("opac", "ketab", "nlai", "openlibrary", "google")
PRIMARY_SOURCES = ("opac", "ketab", "nlai")      # رکورد کامل از هر کدوم ← منتظر بقیه نمی‌مونیم
FIELD_PRIORITY = {"cover_url": ("openlibrary", "google")}     # جلد: Open Library بهتر از گوگل
MERGE_FIELDS = ("title", "subtitle", "authors", "translators", "publisher", "year", "year_calendar", "edition_no", "volume",
                "pages", "language", "subjects", "description", "cover_url")
GRACE_AFTER_COMPLETE = 0.6    # ثانیه
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="isbn")
_BREAKER_LOCK = threading.Lock()


def title_key(title):
    """کلید مقایسه‌ی «همون عنوان»: نرمال‌شده، بدون فاصله و نشانه‌گذاری."""
    from common.text import normalize as text_normalize

    return re.sub(r"[^\w]", "", text_normalize(title or ""))


def merge_records(records):
    """
    records: {نام منبع: دیکشنری}. هر فیلد از اولین منبعِ دارای مقدار (به ترتیب اولویت فیلد) برداشته می‌شه.
    اطمینان: ۴۰ یه منبع + ۳۰ دو منبع هم‌عنوان + ۲۰ ناشر/سال + ۱۰ جلد (حداکثر ۱۰۰). provenance نشون می‌ده هر فیلد از کجاست.
    """
    records = {k: v for k, v in records.items() if v}
    if not records:
        return None
    merged, provenance = {}, {}
    for field in MERGE_FIELDS:
        for source in FIELD_PRIORITY.get(field, SOURCE_NAMES):
            value = records.get(source, {}).get(field)
            if value not in (None, "", []):
                merged[field], provenance[field] = value, source
                break
    merged["isbn"] = next(iter(records.values())).get("isbn", "")
    keys = {title_key(r.get("title")) for r in records.values() if r.get("title")}
    confidence = 40
    if len(records) >= 2 and len(keys) == 1:
        confidence += 30
    if merged.get("publisher") or merged.get("year"):
        confidence += 20
    if merged.get("cover_url"):
        confidence += 10
    merged.update(
        author="، ".join(merged.get("authors", [])), sources=[n for n in SOURCE_NAMES if n in records],
        provenance=provenance, confidence=min(confidence, 100),
    )
    return merged


def _complete(record):
    """رکوردی که برای ثبت کتاب کافیه؛ وقتی منبع اصلی چنین رکوردی داد منتظر منبع‌های دیگه نمی‌مونیم."""
    return bool(record and record.get("title") and record.get("authors") and record.get("publisher") and record.get("year"))


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


def active_sources():
    """منبع‌هایی که پرسیده می‌شن، به ترتیب اولویت SOURCE_NAMES (ISBN_SOURCES تو .env؛ گوگل از ایران ۴۰۳ می‌ده)."""
    wanted = list(getattr(settings, "ISBN_SOURCES", SOURCE_NAMES))
    return [n for n in SOURCE_NAMES if n in wanted]


def _budget():
    return float(getattr(settings, "ISBN_BUDGET", 3.0))


def lookup_full(raw, timeout=None):
    """
    منبع‌های بیرونی هم‌زمان و با بودجه‌ی زمانی کل (پیش‌فرض ۳ ثانیه) پرسیده و ادغام می‌شن؛ دیکشنری غنی با
    confidence/provenance یا None. وقتی کتابخانه‌ی ملی رکورد کامل داد زودتر برمی‌گرده.
    نتیجه‌ی منفیِ ناشی از خطا/timeout/منبعِ کنارگذاشته‌شده کش نمی‌شه. همه‌ی کار کش تو همین thread انجام می‌شه.
    """
    isbn = normalize_isbn(raw)
    if not isbn:
        return None
    key = f"isbn2:{isbn}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    budget = float(timeout) if timeout else _budget()
    deadline = time.monotonic() + budget
    funcs = {"opac": _opac, "ketab": _ketab, "nlai": _nlai, "openlibrary": _open_library, "google": _google}   # موقع صدا زدن خونده می‌شن (تست‌ها جایگزین می‌کنن)
    active = active_sources()
    pending = {name: _POOL.submit(funcs[name], isbn, budget) for name in active if not breaker_open(name)}
    results, failed = {}, len(pending) < len(active)
    from .iran_isbn import hyphen_variants

    # کتاب ایرانی: فهرستگان (opac) همه‌ی رکوردهای کتابخانه‌ی ملی جدید رو هم داره؛ اگه opac و ketab بی‌خطا گفتن «نیست»، nlai کند لازم نیست
    decisive = [n for n in ("opac", "ketab") if n in pending] if hyphen_variants(isbn) else []
    errored, skipped = set(), set()
    while pending:
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
                    errored.add(name)
                    breaker_record(name, False)
        if any(_complete(results.get(n)) for n in PRIMARY_SOURCES):
            # رکورد کامل از یه منبع ایرانی دارید؛ برای جلد و تأیید دوم فقط یه مهلت کوتاه به بقیه می‌دیم نه کل بودجه
            deadline = min(deadline, time.monotonic() + GRACE_AFTER_COMPLETE)
        if decisive and pending and all(n in results and n not in errored for n in decisive) and not any(results.values()):
            skipped = set(pending)           # جواب قطعی «نیست» از منبع‌های ایرانی؛ بقیه کنار می‌رن، شکست حساب نمی‌شن
            break
    for name in pending:                 # بودجه تموم شد: منابع معطل شکست حساب می‌شن (thread‌شون خودش با timeout تموم می‌شه)
        if name in skipped:
            continue
        failed = True
        breaker_record(name, False)
    merged = merge_records(results)
    if merged or not failed:
        cache.set(key, merged or {}, 60 * 60 * 24)
    return merged


def lookup(raw, timeout=None):
    """سازگاری با کد قدیمی: همون lookup_full (شامل کلیدهای isbn/title/author)."""
    return lookup_full(raw, timeout)
