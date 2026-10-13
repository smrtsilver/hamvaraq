#!/usr/bin/env bash
# Lighthouse موبایل روی لیست/جزئیات/فرم (فرم با کوکی نشست). هدف: performance ≥ 90، accessibility = 100، CLS < 0.05.
#   BASE_URL=http://127.0.0.1:8000 SESSION_ID=<sessionid عضو> ./scripts/lighthouse_check.sh
set -euo pipefail
BASE="${BASE_URL:-http://127.0.0.1:8000}"; LH="${LIGHTHOUSE:-npx lighthouse}"
for spec in "books:/books/" "detail:/books/1/" "form:/books/new/"; do
  name="${spec%%:*}"; path="${spec#*:}"
  extra='{}'; [ "$name" = form ] && extra="{\"Cookie\":\"sessionid=${SESSION_ID:?SESSION_ID لازمه}\"}"
  $LH "$BASE$path" --only-categories=performance,accessibility,best-practices,seo --form-factor=mobile \
      --chrome-flags="--headless=new --no-sandbox" --extra-headers="$extra" --output=json --output-path="/tmp/lh_$name.json" --quiet
  python3 - "$name" <<'PY'
import json, sys
d = json.load(open(f"/tmp/lh_{sys.argv[1]}.json"))
c = {k: round(v["score"] * 100) for k, v in d["categories"].items()}
print(sys.argv[1], c, "CLS", round(d["audits"]["cumulative-layout-shift"]["numericValue"], 3))
PY
done
