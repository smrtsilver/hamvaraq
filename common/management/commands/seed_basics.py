from django.core.management import call_command
from django.core.management.base import BaseCommand

from books.models import Category

CATEGORIES = [
    "رمان", "داستان کوتاه", "شعر", "تاریخ", "فلسفه", "روان‌شناسی", "جامعه‌شناسی",
    "علمی", "کامپیوتر", "درسی و دانشگاهی", "کودک و نوجوان", "هنر", "دین و معنویت",
    "اقتصاد و مدیریت", "زندگینامه", "سایر",
]


class Command(BaseCommand):
    help = "استان‌ها، شهرها و دسته‌های پایه رو می‌سازه (چندبار اجرا بی‌خطره)"

    def handle(self, *args, **options):
        call_command("seed_iran_locations", stdout=self.stdout)
        call_command("seed_site_settings", stdout=self.stdout)
        for name in CATEGORIES:
            Category.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("داده‌های پایه آماده شد."))
