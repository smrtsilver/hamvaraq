"""ساخت فایل تقویم (iCalendar) برای «افزودن به تقویم»."""

from datetime import timedelta, timezone as dt_timezone


def _escape(text):
    return str(text or "").replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")


def _fold(line):
    """خطوط بیش از ۷۵ بایت طبق RFC 5545 شکسته می‌شن (بایتی، نه نویسه‌ای؛ فارسی ۲ بایتیه)."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > (74 if parts else 75):
            parts.append(current)
            current = b""
        current += b
    parts.append(current)
    return "\r\n ".join(p.decode("utf-8") for p in parts)


def build(item, url):
    def utc(dt):
        return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    start = item.starts_at
    end = item.ends_at or (start + timedelta(hours=2))
    location = item.place_label + (f" ({item.address})" if item.address and not item.is_online else "")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//hamvaraq//announcements//FA", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT", f"UID:announcement-{item.pk}@hamvaraq", f"DTSTAMP:{utc(item.published_at or item.created_at)}",
        f"DTSTART:{utc(start)}", f"DTEND:{utc(end)}", f"SUMMARY:{_escape(item.title)}",
        f"DESCRIPTION:{_escape(item.summary + chr(10) + chr(10) + url)}", f"LOCATION:{_escape(location)}", f"URL:{url}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
