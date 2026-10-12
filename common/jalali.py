"""تاریخ جلالی و ارقام فارسی. همه‌ی زمان‌ها قبل از تبدیل به منطقه‌ی زمانی تهران می‌رن."""

import datetime

import jdatetime
from django.utils import timezone

_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def fa_digits(value):
    return str(value).translate(_FA)


def _to_j(value):
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return jdatetime.datetime.fromgregorian(datetime=value)
    if isinstance(value, datetime.date):
        return jdatetime.date.fromgregorian(date=value)
    return None


def jdate(value, long=False):
    """۱۴۰۵/۰۷/۲۰ یا (long) ۲۰ مهر ۱۴۰۵."""
    j = _to_j(value)
    if j is None:
        return ""
    if long:
        return fa_digits(f"{j.day} {MONTHS[j.month - 1]} {j.year}")
    return fa_digits(f"{j.year:04d}/{j.month:02d}/{j.day:02d}")


def jtime(value):
    j = _to_j(value)
    return fa_digits(f"{j.hour:02d}:{j.minute:02d}") if isinstance(j, jdatetime.datetime) else ""


def jdatetime_str(value):
    return f"{jdate(value)} {jtime(value)}".strip()


def ago(value, now=None):
    """«۳ ساعت پیش»؛ بعد از یک هفته تاریخ جلالی."""
    now = now or timezone.now()
    seconds = int((now - value).total_seconds())
    if seconds < 60:
        return "همین الان"
    for unit, size in (("دقیقه", 60), ("ساعت", 3600), ("روز", 86400)):
        if seconds < size * (60 if size == 60 else 24 if size == 3600 else 7):
            return fa_digits(f"{seconds // size} {unit} پیش")
    return jdate(value)
