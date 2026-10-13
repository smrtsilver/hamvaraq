"""امتیاز کیفیت آگهی کتاب (۰ تا ۱۰۰) + پیشنهاد برای بهتر شدنش. همین وزن‌ها برای پیش‌نمایش زنده‌ی فرم هم به JS داده می‌شن."""

WEIGHTS = {"base": 25, "cover": 30, "description": 15, "category": 10, "edition_backed": 15, "edition_user": 8, "photos": 5}
DESCRIPTION_MIN = 20


def label(score):
    return "عالی" if score >= 85 else "خوب" if score >= 65 else "قابل بهبود"


def listing_quality(book):
    """{'score','label','tips'}؛ بدون کوئری اضافه‌ی سنگین (photos/edition باید prefetch/select شده باشن تا N+1 نشه)."""
    score, tips = WEIGHTS["base"], []
    if book.cover:
        score += WEIGHTS["cover"]
    else:
        tips.append("عکس جلد اضافه کن؛ مهم‌ترین عامل برای درخواست گرفتنه.")
    if len((book.description or "").strip()) >= DESCRIPTION_MIN:
        score += WEIGHTS["description"]
    else:
        tips.append("چند جمله درباره‌ی وضعیت کتاب بنویس (مثلاً خط‌خوردگی یا یادداشت).")
    if book.category_id:
        score += WEIGHTS["category"]
    else:
        tips.append("دسته‌ی کتاب رو انتخاب کن تا راحت‌تر پیدا بشه.")
    edition = book.edition if book.edition_id else None
    if edition and edition.is_source_backed:
        score += WEIGHTS["edition_backed"]
    elif edition:
        score += WEIGHTS["edition_user"]
        tips.append("شابک هنوز از منبع معتبر تأیید نشده؛ شابک دقیق پشت جلد رو بررسی کن.")
    else:
        tips.append("شابک رو بنویس یا اسکن کن تا مشخصات کتاب کامل بشه.")
    if book.pk and len(book.photos.all()) >= 1:
        score += WEIGHTS["photos"]
    else:
        tips.append("یه عکس از پشت جلد یا داخل کتاب هم اضافه کن.")
    return {"score": score, "label": label(score), "tips": tips}
