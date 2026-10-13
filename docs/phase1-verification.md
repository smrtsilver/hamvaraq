# فاز ۱ — کاتالوگ و شابک: استقرار، برگشت و تأیید

## مهاجرت و بک‌فیل (ایمن؛ فیلدهای قدیمی حذف نمی‌شن)
```bash
./update.sh prod                                                    # migrate: books 0010 (Edition + Book.edition نال‌پذیر)
docker compose -f docker-compose.prod.yml exec -T web python manage.py backfill_editions --dry-run   # فقط گزارش
docker compose -f docker-compose.prod.yml exec -T web python manage.py backfill_editions             # وصل‌کردن کتاب‌های دارای شابک + یکدست‌شدن به ISBN-13
docker compose -f docker-compose.prod.yml exec -T web python manage.py backfill_editions --fetch --sleep 1 --limit 200   # (اختیاری) غنی‌سازی از منبع‌ها
```
- هر بار قابل اجراست (idempotent). شابک نامعتبر دست‌نخورده می‌ماند و فقط گزارش می‌شود.
- **تصمیم ۱ (از طرح): فیلدهای قدیمی نگه داشته شدند** (`Book.title/author/isbn`)؛ `Book.edition` اختیاری و `PROTECT` است.

## رفتار جدید
| بخش | رفتار |
|---|---|
| اعتبارسنجی | رقم کنترل ISBN-10/13، ارقام فارسی/عربی، ISBN-10 → ISBN-13؛ فرم، ثبت دسته‌ای و API خطای فارسی می‌دهند (API: `400 invalid_isbn`) |
| خط‌لوله | NLAI + Open Library + Google هم‌زمان، بودجه‌ی ۳ ثانیه، breaker (۳ شکست → ۵ دقیقه)، ادغام فیلد‌به‌فیلد (فارسی: ملی > OL > گوگل؛ جلد: OL > گوگل)، پس از رکورد کامل ملی فقط ۰٫۶ ثانیه مهلت به بقیه |
| اطمینان | ۴۰ تک‌منبع + ۳۰ دو منبع هم‌عنوان + ۲۰ ناشر/سال + ۱۰ جلد |
| ضد مسموم‌سازی | داده‌ی کاربر: `source=user`, `confidence=20`؛ هرگز داده‌ی منبع‌دار را بازنویسی نمی‌کند؛ هر کاربر مستقلِ هم‌عنوان +۱۵ (سقف ۶۰)؛ عنوان ناهم‌خوان فقط در `provenance.conflicts` |
| کش | Edition ذخیره‌شده = صفر تماس شبکه؛ نتیجه‌ی منفی ۲۴ ساعت؛ Edition کاربری هفته‌ای یک‌بار دوباره پرسیده می‌شود |
| اسکن | `BarcodeDetector` و در غیابش zxing محلی (`static/vendor/zxing`، Apache-2.0)؛ حالت تکی + پیوسته (ثبت دسته‌ای ۱۲ ردیف) |
| UX | پیش‌نمایش زنده، شمارنده‌ی «N نفر دنبال این کتاب»، هشدار کتاب تکراری، امتیاز کیفیت آگهی (۰–۱۰۰)، بلوک مشخصات چاپ در صفحه‌ی کتاب |

## برگشت
1. `git checkout <commit-قبلی> && ./update.sh prod` — مایگریشن `books 0009` برمی‌گرداند (`migrate books 0009`): `Edition` و `Book.edition` حذف می‌شوند ولی `Book.isbn` (که ISBN-13 شده) و همه‌ی داده‌ی قدیمی می‌مانند.
2. فقط پیش‌نمایش/اسکن: فایل‌های `static/js/scan.js` و `preview.js` را از `{% block scripts %}` قالب‌ها بردارید؛ فرم بدون آنها کار می‌کند.

## چک‌لیست تأیید
```
[ ] شابک با رقم کنترل غلط در فرم و API رد می‌شود                                  ← NormalizationTests, IsbnApiTests
[ ] ISBN-10 و ISBN-13 یک کتاب = یک Edition                                        ← CatalogTests.test_isbn10_and_isbn13...
[ ] ISBN ناموجود ≤۳ ثانیه (منبع کند شبیه‌سازی شد)؛ هیچ worker بیش از بودجه گرفته نمی‌شود  ← test_phase0.IsbnBudgetTests
[ ] استعلام دوم همان شابک صفر تماس شبکه                                           ← CatalogTests
[ ] داده‌ی کاربر داده‌ی منبع‌دار را بازنویسی نمی‌کند؛ دو کاربر مستقل اطمینان را بالا می‌برند ← CatalogTests
[ ] بک‌فیل idempotent و فیلدهای قدیمی دست‌نخورده                                   ← BackfillCommandTests
[ ] اسکن تکی و پیوسته (تست مرورگر با دوربین مجازی: ۳ کتاب پشت‌سرهم، zxing)           ← دستی/Playwright (scripts در تاریخچه‌ی کار)
[ ] >۸۰٪ از ۳۰ شابک فارسی: عنوان+نویسنده+ناشر                                     ← python manage.py isbn_coverage docs/isbn-sample.txt  (روی سرور با اینترنت)
[ ] اسکن در Chrome اندروید و Safari iOS واقعی                                      ← فقط روی دستگاه واقعی قابل تأیید است
[ ] ۱۰ کتاب پشت‌هم با اسکن < ۲ دقیقه                                              ← دستی روی گوشی
```
اجرای تست‌ها: `python manage.py test common.test_phase1`
