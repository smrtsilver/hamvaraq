"""نرمال‌سازی متن فارسی برای جستجو و تطبیق (ک/ی عربی، ارقام، نیم‌فاصله، اعراب)."""

import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_CHARS = str.maketrans({
    "ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
    "أ": "ا", "إ": "ا", "ٱ": "ا", "ؤ": "و",
})
# اعراب، کشیده، نیم‌فاصله و کنترل‌های جهت‌دهی
_STRIP = re.compile("[ً-ٰٟـ‌‍‎‏‪-‮]")
_SPACES = re.compile(r"\s+")


def normalize(text):
    """فرم استاندارد برای مقایسه: بدون اعراب/نیم‌فاصله، ی و ک فارسی، رقم لاتین، حروف کوچک."""
    if not text:
        return ""
    text = str(text).translate(_DIGITS).translate(_CHARS)
    text = _STRIP.sub("", text).lower()
    return _SPACES.sub(" ", text).strip()


def words(text):
    return normalize(text).split()


# کلمه‌های خیلی رایج که تنهایی «کتاب مشخصی» رو نشون نمی‌دن (نرمال‌شده)؛ آرزوی «کتاب» یا «ا» نباید به همه اعلان بده
STOPWORDS = frozenset(normalize(w) for w in (
    "کتاب کتابی کتابها رمان جلد چاپ نسخه نسخه‌ی مجموعه داستان شعر ترجمه اثر نویسنده مولف مترجم انتشارات نشر "
    "از به در با برای که این آن را و یا تا بر هم یک دو سه من تو ما").split())
MIN_WORD_LEN = 3


def significant_words(text):
    """کلمه‌های معنی‌دار برای تطبیق آرزو: حداقل ۳ حرف، نه کلمه‌ی رایج. ترتیب حفظ و تکرار حذف می‌شه."""
    return list(dict.fromkeys(w for w in words(text) if len(w) >= MIN_WORD_LEN and w not in STOPWORDS))


def work_key(title, author):
    """کلید «همین کتاب»: عنوان و نویسنده‌ی نرمال‌شده بدون فاصله."""
    return f"{normalize(title).replace(' ', '')}|{normalize(author).replace(' ', '')}"
