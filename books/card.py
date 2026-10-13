"""کارت اشتراک‌گذاری کتاب برای استوری (PNG عمودی ۱۰۸۰×۱۹۲۰) با Pillow."""

import hashlib
import io
import os
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
    return ImageFont.truetype(str(FONTS / f"Vazirmatn-{'ExtraBold' if bold else 'Medium'}.ttf"), size,
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


def _gradient(size, top, bottom):
    w, h = size
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        col.putpixel((0, y), tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return col.resize((w, h))


def _pill(draw, cx, y, text, font, fill, ink):
    shaped = shape(text)
    w = font.getlength(shaped)
    draw.rounded_rectangle((cx - w / 2 - 36, y, cx + w / 2 + 36, y + 84), 42, fill=fill)
    draw.text((cx - w / 2, y + 14), shaped, font=font, fill=ink)


def render_card(book, site_url=None):
    """کارت استوری: زمینه‌ی گرادیان، جلد با سایه، عنوان درشت (ExtraBold)، برچسب شهر/وضعیت و دکمه‌ی دعوت."""
    site_url = site_url or getattr(settings, "SITE_URL", "hamvaraq.ir")
    img = _gradient((W, H), (47, 133, 90), (24, 70, 50))
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse((-260, -260, 520, 520), fill=(255, 255, 255, 14))
    d.ellipse((620, 1250, 1400, 2030), fill=(224, 164, 58, 28))

    _center(d, 80, "هم‌ورق", _font(True, 92), CREAM)
    _center(d, 200, "کتاب بده، کتاب بگیر", _font(False, 42), (214, 240, 224))

    box = (270, 330, 810, 1050)
    cw, ch = box[2] - box[0], box[3] - box[1]
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0] + 10, box[1] + 28, box[2] + 10, box[3] + 28), 24, fill=(0, 0, 0, 120))
    from PIL import ImageFilter
    img.paste(shadow.filter(ImageFilter.GaussianBlur(26)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(26)))
    d = ImageDraw.Draw(img, "RGBA")
    cover = _cover(book)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw, ch), 22, fill=255)
    if cover:
        scale = max(cw / cover.width, ch / cover.height)
        cover = cover.resize((round(cover.width * scale), round(cover.height * scale)))
        left, top = (cover.width - cw) // 2, (cover.height - ch) // 2
        tile = cover.crop((left, top, left + cw, top + ch))
    else:
        tile = _gradient((cw, ch), (224, 164, 58), (160, 100, 20))
        td = ImageDraw.Draw(tile)
        td.rounded_rectangle((26, 26, cw - 26, ch - 26), 14, outline=(255, 255, 255), width=3)
        for i, line in enumerate(wrap(book.title, _font(True, 64), cw - 140, 3)):
            _center_in(td, cw, 190 + i * 90, line, _font(True, 64), (255, 255, 255))
    img.paste(tile, box[:2], mask)
    d.rounded_rectangle((box[0], box[1], box[0] + 14, box[3]), 8, fill=(0, 0, 0, 55))      # عطف کتاب

    title_font = _font(True, 80)
    y = 1130
    for line in wrap(book.title, title_font, W - 140, 2):
        _center(d, y, line, title_font, CREAM)
        y += 110
    _center(d, y + 6, book.author, _font(False, 54), (214, 240, 224))
    f = _font(True, 40)
    _pill(d, W / 2 - 170, y + 120, str(book.city), f, (255, 255, 255, 38), CREAM)
    _pill(d, W / 2 + 190, y + 120, book.get_condition_display(), f, (224, 164, 58, 230), (42, 29, 0))

    d.rounded_rectangle((120, H - 330, W - 120, H - 110), 80, fill=CREAM)
    _center(d, H - 305, "کتاب بعدیت شاید همین باشه", _font(True, 56), DARK)
    _center(d, H - 210, site_url, _font(False, 42), GREEN)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _center_in(draw, width, y, text, font, fill):
    shaped = shape(text)
    draw.text(((width - font.getlength(shaped)) / 2, y), shaped, font=font, fill=fill)


CARD_TEMPLATE_VERSION = "3"      # طراحی کارت عوض شد این رو بالا ببر تا همه‌ی کارت‌های کش‌شده دوباره ساخته بشن


def card_version(book, site_url=None):
    """اثر انگشت محتوای کارت؛ هر چیزی که روی تصویر اثر داره تو آن هست (نه زمان)."""
    site_url = site_url or getattr(settings, "SITE_URL", "hamvaraq.ir")
    raw = "|".join([CARD_TEMPLATE_VERSION, book.title, book.author, str(book.city), book.get_condition_display(), book.cover.name or "", book.cover_thumb.name or "", site_url])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def cards_dir():
    path = Path(settings.MEDIA_ROOT) / "cards"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cached_card_path(book):
    return cards_dir() / f"{book.pk}-{card_version(book)}.png"


def render_to_disk(book):
    """کارت رو می‌سازه و اتمیک روی دیسک می‌نویسه (تلاش هم‌زمان دو درخواست فایل نیمه‌کاره نمی‌سازه)؛ نسخه‌های قدیمی همین کتاب پاک می‌شن."""
    path = cached_card_path(book)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_bytes(render_card(book))
    os.replace(tmp, path)
    for old in path.parent.glob(f"{book.pk}-*.png"):
        if old != path:
            old.unlink(missing_ok=True)
    return path
