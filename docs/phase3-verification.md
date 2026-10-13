# فاز ۳ — UI/UX: استقرار، برگشت و تأیید

## مهاجرت و بک‌فیل تصویر
```bash
./update.sh prod                                                                  # migrate: books 0011 (فیلدهای WebP/ابعاد/LQIP)
docker compose -f docker-compose.prod.yml exec -T web python manage.py generate_image_variants   # کتاب‌های قدیمی؛ idempotent
```
`generate_image_variants --force` همه را دوباره می‌سازد. JPEG اصلی همیشه می‌ماند (fallback).

## چه چیزی عوض شد
| مورد | رفتار |
|---|---|
| فهرست | مرتب‌سازی (جدیدترین/نزدیک‌ترین/پرتقاضاترین)، چیپ فیلتر فعال با ×، «فقط موجود» پیش‌فرض، «ذخیره‌ی جستجو» (با روشن‌شدن لیست آرزو) |
| کارت | وضعیت فیزیکی، نشان «پرتقاضا» (≥۲ درخواست در ۳۰ روز)، هم‌شهری/هم‌استان، «معتبر» (≥۳ رأی و ≥۹۰٪)؛ دو کوئری جمعی (بدون N+1) |
| جزئیات | مشخصات چاپ، «کتاب‌های دیگر کاربر»، اشتراک‌گذاری (Web Share/کپی لینک)، نوار ثابت موبایل، توضیح نگه‌داشتن امتیاز، تقاضا |
| فرم | موبایل ۳ قدمی، فشرده‌سازی کلاینت (۱۶۰۰px/JPEG ۸۲)، اسکن، پیش‌نمایش زنده |
| تصویر | `<picture>` WebP (۴۲۰/۹۶۰) + JPEG، width/height واقعی، LQIP، `fetchpriority=high` فقط اولین کارت/جلد صفحه‌ی جزئیات، `decoding=async` |
| CSP-ready | صفر `style=`، `on*=`، `javascript:` و `<style>` در قالب‌ها (تست می‌شود)؛ هدر CSP با nonce (پیش‌فرض Report-Only) |
| دسترس‌پذیری | axe-core: صفر تخلف روی ۱۱ صفحه × روشن/تیره × موبایل/دسکتاپ؛ ترتیب heading و برچسب‌ها اصلاح شد |

## روشن‌کردن CSP
1. چند روز با `CSP_ENFORCE=False` بماند و لاگ `csp` (و مسیر `/csp-report/`) را ببینید؛ هیچ تخلفی نباید باشد.
2. `.env`: `CSP_ENFORCE=True` و `./update.sh prod`. برگشت: `CSP_ENFORCE=False`.
- ادمین جنگو (`/admin/`) عمداً معاف است (inline زیاد دارد).

## برگشت
1. `git checkout <قبلی> && ./update.sh prod` (مهاجرت: `migrate books 0010`؛ فقط ستون‌های تصویر حذف می‌شوند).
2. فقط تصویر: قالب‌ها به `book.thumb_url` برگردند (تگ `book_cover` اختیاری است) یا `rm -rf media/books/webp`.

## نتایج اندازه‌گیری (Lighthouse موبایل، سرور توسعه)
| صفحه | Performance | Accessibility | Best-practices | CLS |
|---|---|---|---|---|
| فهرست | ۹۴ | ۱۰۰ | ۱۰۰ | ۰٫۰۰۰ |
| جزئیات | ۹۷ | ۱۰۰ | ۱۰۰ | ۰٫۰۰۱ |
| فرم ثبت (SEO=۶۶ چون noindex عمدی) | ۹۶ | ۱۰۰ | ۱۰۰ | ۰٫۰۰۰ |

## چک‌لیست تأیید
```
[ ] Lighthouse موبایل: perf ≥ 90 و a11y = 100 روی فهرست/جزئیات/فرم          ← scripts/lighthouse_check.sh (روی پروداکشن هم اجرا کنید)
[ ] CLS < 0.05                                                              ← همان اسکریپت
[ ] صفر style="" و javascript: در قالب‌ها                                    ← test_phase0.CspAndTemplateHygieneTests
[ ] axe بدون تخلف                                                            ← python scripts/a11y_audit.py
[ ] مرتب‌سازی/چیپ/نشان کارت                                                  ← test_phase3.BookListTests
[ ] WebP/srcset/LQIP/اولویت تصویر                                            ← test_phase3.CoverImageTests
[ ] فرم ۳ قدمی و فشرده‌سازی (مرورگر واقعی، Playwright)                        ← انجام شد؛ روی گوشی واقعی هم امتحان شود
```
