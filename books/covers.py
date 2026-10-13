"""جلدهای طراحی‌شده: کاربر به‌جای عکس واقعی یکی از این طرح‌ها رو انتخاب می‌کنه و عنوان/نویسنده روش نوشته می‌شه.
همین تابع هم پیش‌نمایش انتخاب‌گر رو می‌سازه هم فایل نهایی رو؛ پس چیزی که کاربر می‌بینه همونیه که ذخیره می‌شه.
کدوم طرح انتخاب شده از نام فایل (dz-<طرح>-…) معلوم می‌شه؛ ستون تازه‌ای لازم نیست."""
import io
import math
import random

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFilter

from .card import _font, shape, wrap

# (کلید، نام، دسته، زمینه‌ی بالا، زمینه‌ی پایین، رنگ متن، رنگ تزئین)
DESIGNS = [
    ("classic", "پارچه‌ای", "کلاسیک", (31, 86, 66), (18, 58, 44), (246, 231, 200), (233, 196, 106)),
    ("persian", "تذهیب", "کلاسیک", (24, 42, 84), (14, 26, 56), (250, 238, 210), (214, 170, 84)),
    ("paper", "کاغذی", "مینیمال", (246, 239, 224), (232, 220, 196), (43, 33, 22), (138, 90, 22)),
    ("noir", "شب", "مینیمال", (24, 24, 28), (8, 8, 10), (245, 240, 230), (224, 164, 58)),
    ("poetic", "شاعرانه", "شاعرانه", (233, 196, 196), (178, 112, 128), (60, 24, 36), (255, 247, 240)),
    ("sunset", "غروب", "شاعرانه", (244, 162, 97), (120, 54, 112), (255, 248, 236), (255, 222, 160)),
    ("kids", "رنگین‌کمان", "کودک و نوجوان", (255, 214, 92), (255, 160, 80), (54, 32, 8), (46, 134, 171)),
    ("science", "دفتر شطرنجی", "علمی و فکری", (34, 94, 104), (20, 58, 66), (236, 248, 246), (126, 214, 196)),
]
KEYS = [d[0] for d in DESIGNS]
CATEGORIES = list(dict.fromkeys(d[2] for d in DESIGNS))
PREFIX = "dz-"


def design(key):
    return next((d for d in DESIGNS if d[0] == key), DESIGNS[0])


def key_of(cover_name):
    """از نام فایل جلد، کلید طرح (یا None اگه عکس واقعیه)."""
    base = (cover_name or "").rsplit("/", 1)[-1]
    if not base.startswith(PREFIX):
        return None
    k = base[len(PREFIX):].split("-")[0].split(".")[0]
    return k if k in KEYS else None


def _gradient(w, h, top, bottom):
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        col.putpixel((0, y), tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return col.resize((w, h))


def _ornament(d, key, w, h, s, accent):
    """تزئین مخصوص هر طرح (s = ضریب اندازه)."""
    a = accent
    if key == "classic":
        for inset, wd in ((34, 4), (48, 2)):
            d.rectangle((inset * s, inset * s, w - inset * s, h - inset * s), outline=a, width=max(1, round(wd * s)))
        d.rectangle((0, 0, round(22 * s), h), fill=(0, 0, 0, 60))
    elif key == "persian":
        cx, cy, r = w / 2, h * 0.17, 56 * s
        for i in range(12):
            ang = i * math.pi / 6
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
            d.ellipse((x - 21 * s, y - 21 * s, x + 21 * s, y + 21 * s), outline=a, width=max(1, round(2 * s)))
        d.ellipse((cx - 24 * s, cy - 24 * s, cx + 24 * s, cy + 24 * s), fill=a)
        d.rectangle((26 * s, 26 * s, w - 26 * s, h - 26 * s), outline=a, width=max(1, round(3 * s)))
    elif key == "paper":
        d.line((w * 0.3, h * 0.25, w * 0.7, h * 0.25), fill=a, width=max(1, round(2 * s)))
        d.line((w * 0.42, h * 0.27, w * 0.58, h * 0.27), fill=a, width=max(1, round(1 * s)))
        d.line((w * 0.42, h * 0.80, w * 0.58, h * 0.80), fill=a, width=max(1, round(1 * s)))
        rnd = random.Random(5)
        for _ in range(int(900 * s * s)):
            d.point((rnd.random() * w, rnd.random() * h), fill=(120, 90, 40, 30))
    elif key == "noir":
        for i in range(5):
            y = h * 0.18 + i * 14 * s
            d.line((w * 0.2, y, w * 0.8, y), fill=a + (int(255 * (1 - i * 0.18)),), width=max(1, round(2 * s)))
        d.polygon([(w / 2, h * 0.82), (w / 2 + 16 * s, h * 0.85), (w / 2, h * 0.88), (w / 2 - 16 * s, h * 0.85)], fill=a)
    elif key == "poetic":
        d.ellipse((w * 0.58, h * 0.08, w * 0.58 + 120 * s, h * 0.08 + 120 * s), fill=a + (200,))
        d.ellipse((w * 0.58 + 30 * s, h * 0.08 - 10 * s, w * 0.58 + 150 * s, h * 0.08 + 110 * s), fill=(233, 196, 196, 255))
        for i in range(3):
            d.arc((w * 0.1 - i * 30 * s, h * 0.78 - i * 20 * s, w * 0.9 + i * 30 * s, h * 1.2), 200, 340, fill=a, width=max(1, round(2 * s)))
    elif key == "sunset":
        d.ellipse((w / 2 - 90 * s, h * 0.80 - 90 * s, w / 2 + 90 * s, h * 0.80 + 90 * s), fill=a + (230,))
        for i in range(6):
            y = h * 0.82 + i * 16 * s
            d.rectangle((0, y, w, y + 6 * s), fill=(120, 54, 112, 255))
    elif key == "kids":
        rnd = random.Random(9)
        colors = [(46, 134, 171), (233, 79, 55), (57, 160, 98), (147, 92, 196), (255, 255, 255)]
        for _ in range(26):
            r = rnd.uniform(8, 26) * s
            x, y = rnd.random() * w, rnd.random() * h
            if 0.26 * h < y < 0.74 * h and 0.08 * w < x < 0.92 * w:
                continue                              # وسط جلد جای عنوانه
            d.ellipse((x - r, y - r, x + r, y + r), fill=rnd.choice(colors) + (170,))
    elif key == "science":
        step = round(22 * s)
        for x in range(0, w, step):
            d.line((x, 0, x, h), fill=a + (40,), width=1)
        for y in range(0, h, step):
            d.line((0, y, w, y), fill=a + (40,), width=1)
        d.ellipse((w * 0.62, h * 0.12, w * 0.62 + 90 * s, h * 0.12 + 90 * s), outline=a, width=max(1, round(3 * s)))
        d.line((w * 0.62 + 45 * s, h * 0.12, w * 0.62 + 45 * s, h * 0.12 + 90 * s), fill=a, width=max(1, round(2 * s)))


def render(key, title, author, width=600):
    """تصویر RGB جلد با نسبت ۲:۳."""
    k, _name, _cat, top, bottom, ink, accent = design(key)
    w, h = width, round(width * 1.5)
    s = width / 600
    img = _gradient(w, h, top, bottom).convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    _ornament(ImageDraw.Draw(layer), k, w, h, s, accent)
    img = Image.alpha_composite(img, layer)
    d = ImageDraw.Draw(img)
    # عنوان و نویسنده؛ اندازه‌ی خودکار تا تو سه خط جا بشه
    title = (title or "بی‌نام").strip()
    size = 74
    while size > 34:
        f = _font(True, round(size * s))
        lines = wrap(title, f, w - 120 * s, 3)
        if len(lines) <= 3 and all(f.getlength(shape(ln)) <= w - 110 * s for ln in lines):
            break
        size -= 4
    lh = round(size * s * 1.45)
    y = h * (0.50 if k not in ("poetic", "sunset") else 0.42) - len(lines) * lh / 2
    for ln in lines:
        sh = shape(ln)
        d.text(((w - f.getlength(sh)) / 2, y), sh, font=f, fill=ink)
        y += lh
    if author:
        fa = _font(False, round(34 * s))
        sa = shape(wrap(author, fa, w - 140 * s, 1)[0])
        d.text(((w - fa.getlength(sa)) / 2, y + 26 * s), sa, font=fa, fill=accent if k in ("paper", "kids") else ink)
    # برند کوچک پایین جلد
    fb = _font(False, round(22 * s))
    sb = shape("هم‌ورق")
    d.text(((w - fb.getlength(sb)) / 2, h - (96 if k in ("classic", "persian") else 64) * s), sb, font=fb, fill=ink + (150,))
    return img.convert("RGB")


def preview_png(key, title, author, width=240):
    buf = io.BytesIO()
    render(key, title, author, width).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def as_upload(key, title, author):
    """ContentFile جلد نهایی (JPEG ۹۰۰×۱۳۵۰) با نامی که طرح رو نگه می‌داره."""
    buf = io.BytesIO()
    render(key, title, author, 900).filter(ImageFilter.SMOOTH_MORE).save(buf, "JPEG", quality=88, optimize=True)
    return ContentFile(buf.getvalue(), name=f"{PREFIX}{key}-cover.jpg")
