from django.core.management.base import BaseCommand

from books.models import Book


class Command(BaseCommand):
    help = "برای کتاب‌های دارای جلد که WebP/ابعاد/LQIP ندارن می‌سازه (idempotent؛ فایل JPEG اصلی دست‌نخورده)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--force", action="store_true", help="همه رو دوباره بساز")

    def handle(self, *args, **opts):
        qs = Book.all_objects.exclude(cover="")
        if not opts["force"]:
            qs = qs.filter(cover_webp="")
        done = failed = 0
        for book in qs.iterator():
            if opts["limit"] and done >= opts["limit"]:
                break
            try:
                book.cover.open("rb")
                book.build_cover_variants()
                book.save(update_fields=["cover_webp", "cover_thumb_webp", "cover_w", "cover_h", "cover_lqip"])
                done += 1
            except Exception as e:      # noqa: BLE001 — یک عکس خراب بقیه رو متوقف نکنه
                failed += 1
                self.stderr.write(f"کتاب {book.pk}: {e}")
            finally:
                book.cover.close()
        self.stdout.write(self.style.SUCCESS(f"ساخته‌شده: {done} · ناموفق: {failed}"))
