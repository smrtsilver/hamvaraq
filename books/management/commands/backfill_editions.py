import time

from django.core.management.base import BaseCommand

from books import catalog
from books.isbn import normalize_isbn
from books.models import Book, Edition


class Command(BaseCommand):
    help = "کتاب‌های دارای شابک رو به Edition وصل می‌کنه (idempotent؛ فیلدهای قدیمی دست‌نخورده می‌مونن جز یکدست‌شدن شابک به ISBN-13)."

    def add_arguments(self, parser):
        parser.add_argument("--fetch", action="store_true", help="Edition‌های کاربری رو از منبع‌های بیرونی غنی کن (کند؛ با --sleep)")
        parser.add_argument("--sleep", type=float, default=1.0, help="ثانیه مکث بین استعلام‌های بیرونی")
        parser.add_argument("--limit", type=int, default=0, help="حداکثر تعداد استعلام بیرونی (۰ = بی‌حد)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        linked = invalid = 0
        books = Book.all_objects.select_related("owner").exclude(isbn="")
        for book in books.filter(edition__isnull=True).iterator():
            if not normalize_isbn(book.isbn):
                invalid += 1
                continue
            if opts["dry_run"]:
                linked += 1
                continue
            if catalog.attach_edition(book):
                linked += 1
        enriched = 0
        if opts["fetch"] and not opts["dry_run"]:
            for edition in Edition.objects.filter(confidence__lte=catalog.USER_MAX_CONFIDENCE).exclude(source__contains="+").iterator():
                if opts["limit"] and enriched >= opts["limit"]:
                    break
                if edition.is_source_backed:
                    continue
                result = catalog.resolve(edition.isbn13, fetch=True)
                enriched += bool(result and result.is_source_backed)
                time.sleep(opts["sleep"])
        self.stdout.write(self.style.SUCCESS(
            f"وصل‌شده: {linked} · شابک نامعتبر (دست‌نخورده): {invalid} · غنی‌شده از منبع: {enriched} · کل Edition: {Edition.objects.count()}"))
