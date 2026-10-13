# فاز ۰ — راهنمای استقرار، برگشت و تأیید

## مهاجرت‌ها (ایمن و قابل تکرار)
```bash
./update.sh prod        # pull + build + migrate + createcachetable
# یا دستی:
docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml exec -T web python manage.py createcachetable   # MAX_ENTRIES جدید روی همان جدول اعمال می‌شود
```
مهاجرت‌ها فقط فیلد/قید اضافه یا `on_delete` را عوض می‌کنند (`Book.deleted_at`، `User.deleted_at`، `Wishlist.isbn`، `WishToken`، PROTECT روی `Exchange`/`Vote`/`Message`/`Review`)؛ هیچ داده‌ای حذف نمی‌شود. بک‌فیل `WishToken` در همان مهاجرت و idempotent است.

## تغییر تنظیمات سرور
| مورد | کجا | توضیح |
|---|---|---|
| gunicorn gthread ۲×۴ | `docker/entrypoint.prod.sh` | `WEB_WORKERS`/`WEB_THREADS` از `.env` قابل تغییر |
| سقف استعلام شابک | `.env`: `ISBN_BUDGET=3.0` | ثانیه؛ کل زمانی که یک استعلام request را نگه می‌دارد |
| کارت استوری از nginx | `.env`: `CARD_X_ACCEL_PREFIX=/_cards/` + بلوک `location /_cards/` در `deploy/hamvaraq.nginx.conf.example` | اختیاری؛ بدون آن Django فایل دیسک را می‌دهد |
| `DEBUG` | پیش‌فرض اکنون `False` | توسعه: `.env.example` را کپی کنید (`DEBUG=True`) |
| cron + بکاپ | `deploy/crontab.example` | `crontab -e` و مسیر پروژه را عوض کنید |

## برگشت (Rollback)
1. کد: `git checkout <commit-قبلی> && ./update.sh prod` (مهاجرت‌ها برگشت‌پذیرند: `migrate books 0007`، `migrate exchanges 0005`، `migrate trust 0003`، `migrate accounts 0003`).
2. فقط gunicorn: `WEB_THREADS=1` و `--worker-class sync` را در entrypoint برگردانید.
3. کارت‌ها: `rm -rf media/cards` و `CARD_X_ACCEL_PREFIX=` خالی.
4. حذف نرم: برای بازگردانی کتاب: پنل ← کتاب‌ها ← «حذف‌شده» ← بازگردانی.

## چک‌لیست تأیید (کپی‌پیست)
```
[ ] کتاب با مبادله‌ی کامل حذف سخت نمی‌شود (فقط پنهان)؛ رأی‌ها می‌مانند            ← test_phase0.SoftDeleteTests
[ ] حذف حساب = ناشناس‌سازی؛ مبادله‌ها/رأی‌های دیگران می‌مانند                     ← AnonymizeAccountTests
[ ] کتاب کاربر مسدود در لیست/جستجو/جزئیات نیست و قابل درخواست نیست                ← BannedOwnerTests
[ ] کش با >۳۰۰ کلید شمارنده‌ی محدودیت را حذف نمی‌کند                              ← InfraTests
[ ] ۲ استعلام شابک با منبع ۴ثانیه‌ای: بقیه‌ی سایت پاسخ می‌دهد و هر استعلام ≤ بودجه ← IsbnBudgetTests
[ ] card.png بار دوم بدون رندر از دیسک می‌آید                                      ← CardCacheTests
[ ] آرزوی «ا» یا «کتاب» اعلان اسپم نمی‌سازد                                       ← WishlistMatchingTests
[ ] /healthz/ با قطع دیتابیس ۵۰۳ می‌دهد                                            ← InfraTests.test_healthz_checks_database
[ ] cron و بکاپ روزانه فعال؛ یک‌بار بازیابی تست شده (روی سرور)
```
اجرای همه‌ی رگرسیون‌ها: `python manage.py test common.test_phase0`

### تأیید روی سرور
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://hamvaraq.ir/healthz/                  # 200
docker compose -f docker-compose.prod.yml stop db; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/healthz/   # 503
docker compose -f docker-compose.prod.yml start db
ls -la media/cards | head                                                               # بعد از دو بار باز کردن card.png یک فایل
./scripts/backup_verify.sh                                                               # OK بکاپ سالم
crontab -l | grep -c hamvaraq
```
