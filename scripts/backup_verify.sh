#!/usr/bin/env bash
# بعد از backup_db: مطمئن می‌شه جدیدترین بکاپ امروز ساخته شده، خالی نیست و (برای Postgres) قابل خوندنه.
# خروجی غیرصفر = مشکل. بازیابی واقعی رو یک‌بار دستی تست کن:
#   docker compose -f docker-compose.prod.yml exec -T db pg_restore -l backups/db-<تاریخ>.dump | head
set -euo pipefail
cd "$(dirname "$0")/.."
latest=$(ls -t backups/db-* 2>/dev/null | head -n1 || true)
[ -n "$latest" ] || { echo "بکاپی پیدا نشد"; exit 1; }
[ -s "$latest" ] || { echo "بکاپ خالیه: $latest"; exit 1; }
age=$(( $(date +%s) - $(stat -c %Y "$latest") ))
[ "$age" -lt 90000 ] || { echo "آخرین بکاپ قدیمیه ($age ثانیه): $latest"; exit 1; }
case "$latest" in
  *.dump) docker compose -f docker-compose.prod.yml exec -T db pg_restore -l "/dev/stdin" < "$latest" > /dev/null || { echo "pg_restore نمی‌تونه بخونه: $latest"; exit 1; } ;;
esac
echo "OK بکاپ سالم: $latest"
