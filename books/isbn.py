"""جستجوی شابک: اول کتاب‌های خود هم‌ورق (هر شابکی که یکی ثبت کرده باشه برای بعدی خودکار پر می‌شه)،
بعد Open Library، بعد Google Books. کتاب‌های فارسی همیشه تو منبع‌های بیرونی نیستن؛ نتیجه‌ی خالی عادیه."""

import json
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
GOOGLE_API = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1"


def normalize(raw):
    """شابک ۱۰ یا ۱۳ رقمی (با خط تیره و فاصله) ← رقم‌های خالص، یا None."""
    isbn = re.sub(r"[\s-]", "", (raw or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))).upper()
    if re.fullmatch(r"\d{13}", isbn) or re.fullmatch(r"\d{9}[\dX]", isbn):
        return isbn
    return None


def _fetch(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


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


def lookup(raw, timeout=4):
    """{'isbn','title','author'} یا None اگه پیدا نشد. خطای شبکه هم None می‌ده (و کش نمی‌شه)."""
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
    failed = False
    for source in (_open_library, _google):
        try:
            result = source(isbn, timeout)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            failed = True
            continue
        if result:
            break
    if result or not failed:
        cache.set(key, result or {}, 60 * 60 * 24)
    return result
