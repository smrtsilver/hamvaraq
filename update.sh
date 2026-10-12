#!/usr/bin/env bash
# استفاده:  ./update.sh          (توسعه)
#           ./update.sh prod     (پروداکشن)
#           ./update.sh seed     (توسعه + داده‌ی نمونه)
set -euo pipefail
cd "$(dirname "$0")"

BRANCH="claude/eager-cori-3hmt6n"
FILE="docker-compose.yml"
[ "${1:-}" = "prod" ] && FILE="docker-compose.prod.yml"
DC="docker compose -f $FILE"

git pull origin "$BRANCH"
$DC up -d --build
$DC exec -T web python manage.py migrate --noinput
$DC exec -T web python manage.py createcachetable
if [ "${1:-}" = "seed" ]; then
  $DC exec -T web python manage.py seed_demo
fi
$DC ps
