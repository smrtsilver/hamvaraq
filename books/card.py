"""کارت اشتراک‌گذاری کتاب برای استوری (PNG عمودی ۱۰۸۰×۱۹۲۰) با Pillow."""

import io
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONTS = Path(settings.BASE_DIR) / "static" / "fonts" / "vazirmatn"
GREEN, DARK, CREAM = (47, 133, 90), (28, 78, 55), (250, 249, 246)
_reshaper = arabic_reshaper.ArabicReshaper()


def _font(bold, size):
    return ImageFont.truetype(str(FONTS / f"Vazirmatn-{'Bold' if bold else 'Regular'}.ttf"), size,
                              layout_engine=ImageFont.Layout.BASIC)


def shape(text):
    """متن فارسی رو برای رسم چپ‌به‌راستِ Pillow آماده می‌کنه (اتصال حروف + ترتیب نمایش)."""
    return get_display(_reshaper.reshape(text))


def wrap(text, font, max_width, max_lines):
    """شکستن خط روی متن منطقی؛ هر خط جدا شکل می‌گیره. بیش از max_lines با … بریده می‌شه."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and font.getlength(shape(trial)) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def _center(draw, y, text, font, fill):
    shaped = shape(text)
    draw.text(((W - font.getlength(shaped)) / 2, y), shaped, font=font, fill=fill)


def _cover(book):
    if book.cover:
        try:
            with Image.open(book.cover.path) as im:
                return im.convert("RGB")
        except (OSError, ValueError):
            pass
    return None


def render_card(book, site_url=None):
    site_url = site_url or getattr(settings, "SITE_URL", "hamvaraq.ir")
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 340, W, H], fill=DARK)

    _center(d, 90, "هم‌ورق", _font(True, 96), CREAM)
    _center(d, 220, "کتاب بده، کتاب بگیر", _font(False, 44), (214, 240, 224))

    # قاب جلد
    box = (240, 340, 840, 1140)
    cover = _cover(book)
    d.rounded_rectangle((box[0] - 16, box[1] - 16, box[2] + 16, box[3] + 16), 28, fill=CREAM)
    if cover:
        cw, ch = box[2] - box[0], box[3] - box[1]
        scale = max(cw / cover.width, ch / cover.height)
        cover = cover.resize((round(cover.width * scale), round(cover.height * scale)))
        left, top = (cover.width - cw) // 2, (cover.height - ch) // 2
        img.paste(cover.crop((left, top, left + cw, top + ch)), box[:2])
    else:
        d.rectangle(box, fill=(198, 246, 213))
        _center(d, 640, "کتاب", _font(True, 120), GREEN)

    title_font = _font(True, 72)
    y = 1190
    for line in wrap(book.title, title_font, W - 160, 2):
        _center(d, y, line, title_font, CREAM)
        y += 100
    _center(d, y + 10, book.author, _font(False, 52), (214, 240, 224))
    meta = f"{book.city} · {book.get_condition_display()}"
    _center(d, y + 100, meta, _font(False, 44), (214, 240, 224))

    _center(d, H - 280, "این کتاب رو رایگان بگیر", _font(True, 64), CREAM)
    _center(d, H - 170, site_url, _font(True, 56), (154, 230, 180))

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
