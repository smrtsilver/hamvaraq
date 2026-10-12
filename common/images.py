"""پردازش عکس‌های آپلودی: حذف EXIF (مکان و دوربین)، اصلاح چرخش، کوچک‌کردن و خروجی JPEG."""

import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

# بمب فشرده‌سازی: عکس با پیکسل خیلی زیاد قبل از باز شدن رد می‌شه
Image.MAX_IMAGE_PIXELS = 40_000_000

MAIN_SIZE = 1280
THUMB_SIZE = 420


def _open(file):
    try:
        file.seek(0)
        img = Image.open(file)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError, SyntaxError):
        raise ValidationError("فایل انتخاب‌شده عکس سالم نیست.")
    # اول چرخش EXIF رو اعمال می‌کنیم، بعد خود EXIF دور ریخته می‌شه
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def _encode(img, max_side, quality):
    img = img.copy()
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)  # بدون exif=…، پس فراداده نمی‌ره
    return buf.getvalue()


def process_upload(file, max_side=MAIN_SIZE):
    """UploadedFile ← ContentFile تمیز و سبک (.jpg). برای فرم‌ها."""
    data = _encode(_open(file), max_side, 85)
    return ContentFile(data, name="photo.jpg")


def make_thumb(file):
    """بند‌انگشتی مربعی‌نما برای گرید کتاب‌ها (نسبت ۳:۴ حفظ می‌شه)."""
    return ContentFile(_encode(_open(file), THUMB_SIZE, 80), name="thumb.jpg")
