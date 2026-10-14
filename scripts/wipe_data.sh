#!/usr/bin/env bash
# پاک کردن همه‌ی داده‌های تست روی سرور (کاربرها، کتاب‌ها، مبادله‌ها، عکس‌ها…) و ساختن یه مدیر تازه.
# شهرها، دسته‌ها و تنظیمات سایت می‌مونن. قبلش بکاپ کامل تو پوشه‌ی backups/ گرفته می‌شه.
# استفاده (روی سرور):  ./scripts/wipe_data.sh
set -euo pipefail
cd "$(dirname "$0")/.."

DC="docker compose -f docker-compose.prod.yml"
$DC exec web python manage.py wipe_data
echo
echo "حالا مدیر (سوپرادمین) جدید رو بساز:"
$DC exec web python manage.py createsuperuser
