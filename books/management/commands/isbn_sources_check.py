"""
مقایسه‌ی منبع‌های استعلام شابک: هر منبع جدا (بدون کش و بدون ادغام) روی چند شابک پرسیده می‌شه و نرخ موفقیت،
زمان و کامل بودن رکورد گزارش می‌شه تا ترتیب ISBN_SOURCES رو بر اساس داده انتخاب کنیم.

    python manage.py isbn_sources_check                      # شابک‌های نمونه‌ی پیش‌فرض
    python manage.py isbn_sources_check 9786229015155 ...    # شابک‌های دلخواه
    python manage.py isbn_sources_check --sources opac,ketab --timeout 8
"""

import time

from django.core.management.base import BaseCommand

from books import isbn as isbn_lib
from books.iran_isbn import hyphenate

# کتاب تازه (فقط فیپا/خانه‌ی کتاب)، کتاب فارسی قدیمی‌تر، ترجمه، و یه کتاب خارجی
SAMPLES = ["9786229015155", "9786227992571", "9786004365758", "9789643416928", "9786006783291", "9780141036144"]


class Command(BaseCommand):
    help = "منبع‌های شابک رو جدا جدا روی چند شابک امتحان می‌کنه و سرعت/موفقیت رو گزارش می‌ده."

    def add_arguments(self, parser):
        parser.add_argument("isbns", nargs="*")
        parser.add_argument("--sources", default=",".join(isbn_lib.SOURCE_NAMES))
        parser.add_argument("--timeout", type=float, default=8.0)

    def handle(self, *args, **opts):
        funcs = {"opac": isbn_lib._opac, "ketab": isbn_lib._ketab, "nlai": isbn_lib._nlai,
                 "openlibrary": isbn_lib._open_library, "google": isbn_lib._google}
        sources = [s for s in opts["sources"].split(",") if s in funcs]
        isbns = [isbn_lib.normalize_isbn(x) for x in (opts["isbns"] or SAMPLES)]
        stats = {s: {"hit": 0, "full": 0, "err": 0, "time": 0.0} for s in sources}
        for isbn in filter(None, isbns):
            self.stdout.write(f"\n{hyphenate(isbn)}")
            for name in sources:
                t = time.monotonic()
                try:
                    rec, err = funcs[name](isbn, opts["timeout"]), ""
                except Exception as e:          # گزارش، نه شکست کل دستور
                    rec, err = None, f"{type(e).__name__}: {str(e)[:60]}"
                dt = time.monotonic() - t
                st = stats[name]
                st["time"] += dt
                if err:
                    st["err"] += 1
                    line = f"خطا ({err})"
                elif rec:
                    st["hit"] += 1
                    st["full"] += isbn_lib._complete(rec)
                    line = f"{rec.get('title', '')[:40]} | {'، '.join(rec.get('authors', []))[:30]} | {rec.get('publisher', '')[:20]} {rec.get('year') or ''}"
                else:
                    line = "پیدا نشد"
                self.stdout.write(f"  {name:12} {dt:5.2f}s  {line}")
        n = len([x for x in isbns if x])
        self.stdout.write("\nخلاصه (پیداشده / کامل / خطا / میانگین زمان):")
        ranked = sorted(sources, key=lambda s: (-stats[s]["full"], -stats[s]["hit"], stats[s]["time"]))
        for name in ranked:
            st = stats[name]
            self.stdout.write(f"  {name:12} {st['hit']}/{n}  {st['full']}/{n}  {st['err']}  {st['time'] / max(1, n):.2f}s")
        self.stdout.write(self.style.SUCCESS("ترتیب پیشنهادی: " + ",".join(ranked)))
