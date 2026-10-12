"""پاک‌سازی و بارگذاری استان‌ها و شهرهای ایران (داده‌ی اولیه از porofam)."""

import json
import re
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "iran_locations.json"

# املای رایج‌تر برای چند شهر بزرگ که تو داده‌ی خام با فاصله اومده
OVERRIDES = {"بندر عباس": "بندرعباس", "خرم آباد": "خرم‌آباد"}
_ARABIC = str.maketrans({"ي": "ی", "ك": "ک"})


def _squash(text):
    return re.sub(r"\s+", " ", str(text).translate(_ARABIC)).strip()


def clean_locations(raw):
    """
    {استان: [شهرها]} ← همون ساختار تمیز:
    - فاصله‌های اضافی و ی/ک عربی اصلاح می‌شه
    - ردیف‌های با پسوند عدد («تبریز۱»، «شهریار۲») که تقسیم‌بندی اداری‌ان حذف می‌شن
    - تکراری‌ها (با نادیده‌گرفتن فاصله) یکی می‌شن؛ خروجی الفبایی
    """
    out = {}
    for province, cities in raw.items():
        province = _squash(province)
        if not province:
            continue
        seen, names = set(), []
        for city in cities:
            city = _squash(city)
            if not city or re.search(r"\d", city):
                continue
            city = OVERRIDES.get(city, city)
            key = city.replace(" ", "").replace("‌", "")
            if key in seen:
                continue
            seen.add(key)
            names.append(city)
        out[province] = sorted(names)
    return dict(sorted(out.items()))


def load_locations(path=None):
    with open(path or DATA_PATH, encoding="utf-8") as f:
        return clean_locations(json.load(f))
