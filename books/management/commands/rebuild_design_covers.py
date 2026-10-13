from django.core.management.base import BaseCommand

from books import covers
from books.models import Book


class Command(BaseCommand):
    help = "جلدهای طراحی‌شده رو با طرح و نسبت فعلی از نو می‌سازه (عکس‌های واقعی دست‌نخورده)."

    def handle(self, *args, **opts):
        done = 0
        for book in Book.all_objects.filter(cover__contains=covers.PREFIX).iterator():
            key = covers.key_of(book.cover.name)
            if not key:
                continue
            book.cover = covers.as_upload(key, book.title, book.author)
            book.save()
            done += 1
        self.stdout.write(self.style.SUCCESS(f"ساخته‌شده: {done}"))
