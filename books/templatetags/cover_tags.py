from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

PRESETS = {
    "card": {"sizes": "(max-width: 600px) 46vw, 260px", "alt": True},
    "hero": {"sizes": "(max-width: 980px) 92vw, 520px", "alt": True},
}


def _scaled(book, max_side):
    w, h = book.cover_w, book.cover_h
    if not (w and h):
        return "", ""
    k = min(1, max_side / max(w, h))
    return round(w * k), round(h * k)


@register.simple_tag
def book_cover(book, preset="card", priority=False, alt=None):
    """
    <picture> برای جلد: WebP با srcset (۴۲۰/۹۶۰)، JPEG برای مرورگر قدیمی، width/height واقعی (CLS صفر)،
    decoding=async، و فقط برای «اولین/مهم‌ترین» عکس fetchpriority=high (بقیه lazy). LQIP با data-lqip و JS.
    """
    if not book.cover:
        return ""
    cfg = PRESETS.get(preset, PRESETS["card"])
    alt = alt if alt is not None else f"جلد کتاب «{book.title}»"
    thumb_url = book.cover_thumb.url if book.cover_thumb else book.cover.url
    src = book.cover.url if preset == "hero" else thumb_url
    width, height = _scaled(book, 960 if preset == "hero" else 420)
    parts = [format_html('<img src="{}" alt="{}"', src, alt)]
    if width:
        parts.append(format_html(' width="{}" height="{}"', width, height))
    parts.append(format_html(' decoding="async"{}', mark_safe(' fetchpriority="high"' if priority else ' loading="lazy"')))
    if preset == "hero":
        parts.append(mark_safe(" data-gallery-main"))
    if book.cover_lqip:
        parts.append(format_html(' data-lqip="{}"', book.cover_lqip))
    img = format_html("{}>", mark_safe("".join(parts)))
    if book.cover_webp and book.cover_thumb_webp:
        srcset = f"{book.cover_thumb_webp.url} 420w, {book.cover_webp.url} 960w"
        return format_html('<picture><source type="image/webp" srcset="{}" sizes="{}">{}</picture>', srcset, cfg["sizes"], img)
    return img
