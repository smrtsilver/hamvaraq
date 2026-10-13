#!/bin/sh
set -e

python manage.py createcachetable
python manage.py migrate --noinput
python manage.py seed_basics
python manage.py collectstatic --noinput

# سرور کم‌حافظه (~۱٫۹ گیگ مشترک با پروژه‌ی دیگه): ۲ پروسه × ۴ thread. gthread یعنی استعلام کند شابک
# یا آپلود عکس فقط یه thread رو می‌گیره، نه کل worker رو.
exec gunicorn HamVaraqDjangoServer.wsgi:application \
    --bind 0.0.0.0:8000 \
    --worker-class gthread \
    --workers "${WEB_WORKERS:-2}" \
    --threads "${WEB_THREADS:-4}" \
    --worker-tmp-dir /dev/shm \
    --max-requests 1000 --max-requests-jitter 100 \
    --timeout 60
