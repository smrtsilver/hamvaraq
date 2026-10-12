"""جستجوی شابک در Open Library. کتاب‌های فارسی همیشه اون‌جا نیستن، پس نتیجه‌ی خالی عادیه."""

import json
import re
import urllib.error
import urllib.request

from django.core.cache import cache

API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"


def normalize(raw):
    """شابک ۱۰ یا ۱۳ رقمی (با خط تیره و فاصله) ← رقم‌های خالص، یا None."""
    isbn = re.sub(r"[\s-]", "", (raw or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))).upper()
    if re.fullmatch(r"\d{13}", isbn) or re.fullmatch(r"\d{9}[\dX]", isbn):
        return isbn
    return None


def lookup(raw, timeout=4):
    """{'isbn','title','author'} یا None اگه پیدا نشد. خطای شبکه هم None می‌ده."""
    isbn = normalize(raw)
    if not isbn:
        return None
    key = f"isbn:{isbn}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    try:
        with urllib.request.urlopen(API.format(isbn=isbn), timeout=timeout) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None  # خطا رو کش نمی‌کنیم
    info = data.get(f"ISBN:{isbn}")
    result = None
    if info and info.get("title"):
        authors = ", ".join(a.get("name", "") for a in info.get("authors", []) if a.get("name"))
        result = {"isbn": isbn, "title": info["title"], "author": authors}
    cache.set(key, result or {}, 60 * 60 * 24)
    return result
