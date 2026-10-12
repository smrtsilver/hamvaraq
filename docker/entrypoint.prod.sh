#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed_basics
python manage.py collectstatic --noinput

exec gunicorn HamVaraqDjangoServer.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 60
