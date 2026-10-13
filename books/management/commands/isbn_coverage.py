import time

from django.core.management.base import BaseCommand, CommandError

from books import isbn as isbn_lib


class Command(BaseCommand):
    help = "پوشش منبع‌های شابک رو روی یه فایل نمونه (هر خط یه شابک) می‌سنجه: چند درصد عنوان+نویسنده+ناشر برمی‌گردونن؟ (نیاز به اینترنت)"

    def add_arguments(self, parser):
        parser.add_argument("file", help="فایل متنی؛ هر خط یک شابک (با # کامنت)")
        parser.add_argument("--sleep", type=float, default=1.0)
        parser.add_argument("--target", type=int, default=80, help="درصد هدف (پیش‌فرض ۸۰)")

    def handle(self, *args, **opts):
        try:
            lines = [ln.split("#")[0].strip() for ln in open(opts["file"], encoding="utf-8")]
        except OSError as e:
            raise CommandError(str(e)) from e
        isbns = [ln for ln in lines if ln]
        full = found = invalid = 0
        for raw in isbns:
            if not isbn_lib.normalize_isbn(raw):
                invalid += 1
                self.stdout.write(f"✗ {raw}: شابک نامعتبر")
                continue
            data = isbn_lib.lookup_full(raw, timeout=6)
            if data:
                found += 1
            ok = bool(data and data.get("title") and data.get("authors") and data.get("publisher"))
            full += ok
            self.stdout.write(f"{'✓' if ok else '·'} {raw}: " + (f"{data['title']} | {data.get('author', '')} | {data.get('publisher', '')} | {','.join(data['sources'])} | {data['confidence']}" if data else "پیدا نشد"))
            time.sleep(opts["sleep"])
        valid = len(isbns) - invalid
        pct = round(100 * full / valid) if valid else 0
        style = self.style.SUCCESS if pct >= opts["target"] else self.style.WARNING
        self.stdout.write(style(f"کامل (عنوان+نویسنده+ناشر): {full}/{valid} = {pct}٪ · پیدا شده: {found} · نامعتبر: {invalid} · هدف: {opts['target']}٪"))
