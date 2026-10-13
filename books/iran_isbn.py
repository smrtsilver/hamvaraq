"""
منبع‌های ایرانی شابک که فقط با شابکِ خط‌تیره‌دارِ دقیق جواب می‌دن:

- opac: فهرستگان کتابخانه‌ی ملی (opac.nlai.ir) — رکورد «فیپا»ی کتاب‌های تازه رو هم داره (libs.nlai.ir نداره)؛
  جستجوی دقیق (tokenized=false) ← صفحه‌ی کامل رکورد در همان نشست.
- ketab: خانه‌ی کتاب (ketab.ir، مرجع صدور شابک) — جستجوی پیشرفته با فیلد شابک ← صفحه‌ی کتاب.

کاربر شابک رو هر جور بنویسه (با/بی خط تیره، ارقام فارسی) به ISBN-13 یکدست می‌شه و خط‌تیره‌ی استاندارد رو
خودمون از روی بازه‌های رسمی گروه‌های ایران (۶۰۰، ۶۲۲، ۹۶۴) می‌سازیم؛ اگه جدول قدیمی بود، تقسیم‌های دیگه هم امتحان می‌شن.
"""

import html
import http.cookiejar
import re
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Mobile Safari/537.36"

# بازه‌های ناشر (registrant) گروه‌های ایران؛ از RangeMessage آژانس بین‌المللی شابک. (از, تا, طول)
IRAN_RANGES = {
    "600": [("00", "09", 2), ("100", "499", 3), ("5000", "8999", 4), ("90000", "99999", 5)],
    "622": [("00", "10", 2), ("200", "459", 3), ("4600", "8749", 4), ("87500", "99999", 5)],
    "964": [("00", "14", 2), ("150", "249", 3), ("2500", "2999", 4), ("300", "549", 3), ("5500", "8999", 4),
            ("90000", "96999", 5), ("970", "989", 3), ("9900", "9999", 4)],
}


def _split(isbn13, reg_len):
    group, rest = isbn13[3:6], isbn13[6:12]
    return f"{isbn13[:3]}-{group}-{rest[:reg_len]}-{rest[reg_len:]}-{isbn13[12]}"


def hyphen_variants(isbn13):
    """
    ISBN-13 ایرانی ← فهرست شکل‌های خط‌تیره‌دار؛ اولی شکل استاندارد (از جدول بازه‌ها)، بقیه تقسیم‌های ممکن دیگه
    (برای وقتی ناشر تو بازه‌ای تازه است). شابک غیرایرانی ← [] (این منبع‌ها فقط کتاب ایرانی دارن).
    """
    if not (isbn13 and len(isbn13) == 13 and isbn13[:3] == "978" and isbn13[3:6] in IRAN_RANGES):
        return []
    rest = isbn13[6:12]
    best = None
    for lo, hi, n in IRAN_RANGES[isbn13[3:6]]:
        if int(lo) <= int(rest[:n]) <= int(hi):
            best = n
            break
    lengths = ([best] if best else []) + [n for n in (4, 3, 5, 2, 1) if n != best]
    return [_split(isbn13, n) for n in lengths]


def hyphenate(isbn13):
    """شکل استاندارد خط‌تیره‌دار (برای نمایش) یا همان رقم‌ها اگه گروهش رو نمی‌شناسیم."""
    variants = hyphen_variants(isbn13)
    return variants[0] if variants else isbn13


# ---------------------------------------------------------------- کمکی‌ها
def _opener():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", UA), ("Accept-Language", "fa,en;q=0.5")]
    return op


def _read(op, url, timeout, data=None, referer=None):
    req = urllib.request.Request(url, data=data, headers={"Referer": referer} if referer else {})
    with op.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _text(fragment):
    """HTML ← متن تمیز (خطوط <br> جدا می‌مونن)."""
    from .isbn import _clean

    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment or "")
    lines = [_clean(html.unescape(re.sub(r"<[^>]+>", " ", part))) for part in fragment.split("\n")]
    return "\n".join(x for x in lines if x)


def _swap_name(name):
    """«خانوادگی، نام» ← «نام خانوادگی» (و حذف سال تولد/وفات)."""
    name = re.sub(r"[\d۰-۹٠-٩]{3,4}\s*[-–]\s*([\d۰-۹٠-٩]{3,4})?\s*(م\.?|ق\.?)?", "", name)
    parts = [p.strip(" ،,.-") for p in re.split(r"\s*[،,]\s*", name) if p.strip(" ،,.-")]
    return " ".join(reversed(parts[:2])) if len(parts) >= 2 else (parts[0] if parts else "")


# «نویسنده»، «نوشته‌ی»، «نویسنده نمایشنامه»… که کتابخانه‌ی ملی جلوی نام می‌ذاره
_ROLE_PREFIX = re.compile(r"^(?:\[?(?:نویسنده|نويسنده|نوشته‌ی|نوشته|سروده‌ی|سروده|تالیف|تألیف|به قلم|اثر|مؤلف|مولف|پدیدآور)\]?)"
                          r"(?:\s+(?:نمایشنامه|متن|داستان|و\s+تصویرگر))?\s+")


def _names(text):
    out = []
    for x in re.split(r"\s*[،,]\s*|\s+و\s+", text or ""):
        x = _ROLE_PREFIX.sub("", x.strip(" .،,[]")).strip(" .،,[]")
        if x:
            out.append(x)
    return out


def _deadline(timeout):
    end = time.monotonic() + timeout

    def left():
        return max(0.3, end - time.monotonic())

    return end, left


# ---------------------------------------------------------------- فهرستگان کتابخانه‌ی ملی (OPAC)
OPAC = "https://opac.nlai.ir/opac-prod/search/"
OPAC_ROLE_TRANSLATOR = re.compile(r"\[?\s*(مترجم|ترجمه|برگردان)[^\]\s]*\s*\]?")
OPAC_OTHER_ROLES = ("ویراستار", "ويراستار", "تصویرگر", "تصويرگر", "به کوشش", "زیر نظر", "گردآوری", "مقدمه", "طراح")


def parse_opac(page, isbn13):
    """صفحه‌ی کامل رکورد OPAC ← دیکشنری؛ None اگه شابکِ رکورد با شابک خواسته‌شده نخونه."""
    from .isbn import _int, _year_info, normalize_isbn

    page = html.unescape(page)
    rows = {}
    for label, value in re.findall(r"(?is)<TR>\s*<TD[^>]*>(.*?)</TD>\s*<TD[^>]*>\s*:\s*</TD>\s*<TD[^>]*>(.*?)</TD>\s*</TR>", page):
        key = re.sub(r"\s+", " ", _text(label)).replace("ي", "ی").replace("ك", "ک")
        rows.setdefault(key, []).append(_text(value))
    isbns = {normalize_isbn(tok) for v in rows.get("شابک", []) for tok in re.findall(r"[\dXx۰-۹-]{10,20}", v)}
    if isbn13 not in isbns:
        return None
    main = (rows.get("عنوان و نام پدیدآور") or [""])[0].split("\n")[0]
    title_part, _, resp = main.partition("/")
    # زیرعنوان بعد از «:» میاد (گاهی با فاصله‌ی قبلش، گاهی بدون)
    title, subtitle = (re.split(r"\s*:\s+", title_part, maxsplit=1) + [""])[:2]
    title = title.strip(" .:")
    if not title:
        return None
    authors, translators = [], []
    segments = [s.strip() for s in resp.split("؛")] if resp else []
    for i, seg in enumerate(segments):
        if OPAC_ROLE_TRANSLATOR.search(seg):
            translators += _names(OPAC_ROLE_TRANSLATOR.sub("", seg))
        elif any(r in seg for r in OPAC_OTHER_ROLES):
            continue
        elif i == 0:
            authors += _names(seg)
    if not authors and rows.get("سرشناسه"):
        swapped = _swap_name(rows["سرشناسه"][0].split("\n")[0])
        authors = [swapped] if swapped else []
    pub = (rows.get("مشخصات نشر") or [""])[0]
    publisher = pub.split(":", 1)[1] if ":" in pub else ""
    publisher = re.split(r"\s*[،,]\s*[\d۰-۹]", publisher)[0].strip(" .،,")
    year, calendar = _year_info(pub)
    edition = (rows.get("وضعیت ویراست") or [""])[0]
    subjects = [v.split("\n")[0].split(" -- ")[0] for v in rows.get("موضوع", [])][:6]
    return {k: v for k, v in {
        "isbn": isbn13, "title": title, "subtitle": subtitle.strip(" .:"), "authors": authors, "translators": translators,
        "publisher": publisher, "year": year, "year_calendar": calendar,
        "pages": _int((rows.get("مشخصات ظاهری") or [""])[0]), "edition_no": edition, "language": "per",
        "subjects": [s for s in dict.fromkeys(subjects) if s],
    }.items() if v not in ("", None, [])}


OPAC_VARIANTS = 3      # شکل استاندارد + دو جایگزین (هر کدوم ~۰٫۲ ثانیه)
KETAB_VARIANTS = 2     # خانه‌ی کتاب کندتره (~۱٫۵ ثانیه برای هر شکل)


def opac(isbn13, timeout):
    """جستجوی دقیق شابک در OPAC؛ شکل استاندارد اول، بعد چند تقسیم دیگه تا تموم شدن بودجه."""
    variants = hyphen_variants(isbn13)[:OPAC_VARIANTS]
    if not variants:
        return None
    end, left = _deadline(timeout)
    op = _opener()
    for variant in variants:
        if time.monotonic() >= end:
            break
        qs = urllib.parse.urlencode({"simpleSearch.value": variant, "command": "I", "simpleSearch.tokenized": "false", "classType": "0",
                                     "pageStatus": "0", "attributes.locale": "fa", "simpleSearch.indexFieldId": "", "documentType": "", "nliHolding": ""})
        page = _read(op, OPAC + "bibliographicSimpleSearchProcess.do?" + qs, left())
        for href in list(dict.fromkeys(re.findall(r'href="([^"]*FULL_VIEW[^"]*)"', page)))[:3]:
            record = parse_opac(_read(op, urllib.parse.urljoin(OPAC, html.unescape(href)), left()), isbn13)
            if record:
                return record
    return None


# ---------------------------------------------------------------- خانه‌ی کتاب (ketab.ir)
KETAB = "https://ketab.ir"
KETAB_FORM = {
    "CurrentPage": "1", "__Invariant": "CurrentPage", "Filter.SkipCount": "0", "Filter.BookTitle": "", "Filter.PublisherTitle": "",
    "Filter.AuthorFirstName": "", "Filter.AuthorLastName": "", "Filter.MinDewey": "", "Filter.MaxDewey": "", "Filter.MinVersionNumber": "",
    "Filter.MaxVersionNumber": "", "btnSubmit": "جستجو", "Filter.DeweyGradeFilter": "", "Filter.SizeTypeId": "", "Filter.CoverTypeId": "",
    "Filter.LanguageId": "", "Filter.ProvinceId": "", "Filter.CityId": "", "Filter.IssuePlaceType": "", "Filter.BookType": "",
    "Filter.StatusFilter": "", "MaxResultCount": "21",
    # بدون بازه‌ی تاریخ نتیجه‌ای برنمی‌گرده؛ بازه‌ی خیلی باز یعنی «همه»
    "dateFrom": "1300/01/01", "dateTo": "1499/12/29",
}


def parse_ketab(page, isbn13):
    """صفحه‌ی کتاب خانه‌ی کتاب ← دیکشنری؛ None اگه شابکش نخونه."""
    from .isbn import _clean, _int, normalize_isbn

    rows = {}
    for label, value in re.findall(r'(?s)text-muted">\s*([^<]+?)\s*</div>\s*<div class="[^"]*boldTr[^"]*">(.*?)</div>', page):
        rows.setdefault(_clean(html.unescape(label)), value)
    if normalize_isbn(_text(rows.get("شابک", ""))) != isbn13:
        return None
    h1 = re.search(r'(?s)<h1[^>]*card-title[^>]*>(.*?)</h1>', page)
    title = _text(h1.group(1)) if h1 else ""
    if not title:
        return None
    authors, translators = [], []
    for role, name in re.findall(r"(?s)<span[^>]*>\s*([^<:]+?)\s*:\s*<a[^>]*>(.*?)</a>", rows.get("پدیدآور", "")):
        role, name = _clean(html.unescape(role)).replace("ي", "ی"), _swap_name(_text(name))
        if not name:
            continue
        if "مترجم" in role or "ترجم" in role:
            translators.append(name)
        elif any(w in role for w in ("نویسنده", "پدیدآور", "مؤلف", "مولف", "شاعر", "گردآورنده")):
            authors.append(name)
    spec = _text(rows.get("مشخصات", ""))
    pages = re.search(r"([\d۰-۹]+)\s*صفحه", spec)
    edition = re.search(r"چاپ\s*([\d۰-۹]+)", spec)
    date = re.sub(r"\D", "", _text(rows.get("تاریخ نشر", "")))
    year = int(date[:4]) if len(date) >= 4 else None
    return {k: v for k, v in {
        "isbn": isbn13, "title": title, "authors": list(dict.fromkeys(authors)), "translators": list(dict.fromkeys(translators)),
        "publisher": _text(rows.get("ناشر", "")), "year": year, "year_calendar": "jalali" if year and year < 1700 else ("gregorian" if year else ""),
        "pages": _int(pages.group(1)) if pages else None, "edition_no": f"چاپ {edition.group(1)}" if edition else "",
        "language": _text(rows.get("زبان کتاب", "")),
    }.items() if v not in ("", None, [])}


def ketab(isbn13, timeout):
    """جستجوی پیشرفته‌ی خانه‌ی کتاب با فیلد شابک (توکن ضد جعل + کوکی همان نشست) ← صفحه‌ی کتاب."""
    variants = hyphen_variants(isbn13)[:KETAB_VARIANTS]
    if not variants:
        return None
    end, left = _deadline(timeout)
    op = _opener()
    form = _read(op, KETAB + "/advanced-search", left())
    token = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', form)
    if not token:
        raise ValueError("ketab.ir: antiforgery token not found")
    for variant in variants:
        if time.monotonic() >= end:
            break
        data = urllib.parse.urlencode(dict(KETAB_FORM, **{"Filter.Isn": variant, "__RequestVerificationToken": token.group(1)})).encode()
        page = _read(op, KETAB + "/advanced-search", left(), data=data, referer=KETAB + "/advanced-search")
        for path in list(dict.fromkeys(re.findall(r'href="(/book/[0-9a-fA-F-]{36})"', page)))[:3]:
            record = parse_ketab(_read(op, KETAB + path, left()), isbn13)
            if record:
                return record
    return None
