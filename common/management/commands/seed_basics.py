from django.core.management.base import BaseCommand

from books.models import Category
from common.models import City

CITIES = [
    "تهران", "مشهد", "اصفهان", "شیراز", "تبریز", "کرج", "اهواز", "قم", "کرمانشاه",
    "ارومیه", "رشت", "زاهدان", "کرمان", "همدان", "یزد", "اردبیل", "بندرعباس",
    "اراک", "زنجان", "سنندج", "قزوین", "گرگان", "ساری", "بوشهر", "خرم‌آباد",
]
CATEGORIES = [
    "رمان", "داستان کوتاه", "شعر", "تاریخ", "فلسفه", "روان‌شناسی", "جامعه‌شناسی",
    "علمی", "کامپیوتر", "درسی و دانشگاهی", "کودک و نوجوان", "هنر", "دین و معنویت",
    "اقتصاد و مدیریت", "زندگینامه", "سایر",
]


class Command(BaseCommand):
    help = "شهرها و دسته‌های پایه رو می‌سازه (چندبار اجرا بی‌خطره)"

    def handle(self, *args, **options):
        for name in CITIES:
            City.objects.get_or_create(name=name)
        for name in CATEGORIES:
            Category.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("شهرها و دسته‌ها آماده شد."))
