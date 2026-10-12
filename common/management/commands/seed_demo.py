"""داده‌ی نمونه برای توسعه و تست دستی (کاربر، کتاب با جلد، مبادله، نقطه‌ی تحویل، چالش). فقط با DEBUG=True."""

import io
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image, ImageDraw

from accounts.models import User
from books.models import Book, Category, Review, Wishlist
from challenges.models import Challenge
from common.models import City, MeetingPoint
from exchanges import services

PASSWORD = "demo12345"
USERS = [("sara", "تهران"), ("ali", "اصفهان"), ("maryam", "شیراز"), ("reza", "تهران"), ("neda", "مشهد")]
BOOKS = [
    ("بوف کور", "صادق هدایت", "رمان", "تهران", "sara"), ("کلیدر", "محمود دولت‌آبادی", "رمان", "مشهد", "neda"),
    ("سووشون", "سیمین دانشور", "رمان", "شیراز", "maryam"), ("شازده کوچولو", "آنتوان دوسنت اگزوپری", "کودک و نوجوان", "اصفهان", "ali"),
    ("گلستان سعدی", "سعدی", "شعر", "شیراز", "maryam"), ("تاریخ بیهقی", "ابوالفضل بیهقی", "تاریخ", "تهران", "reza"),
    ("جنایت و مکافات", "فئودور داستایفسکی", "رمان", "اصفهان", "ali"), ("مقدمه‌ای بر روان‌شناسی", "ریتا اتکینسون", "روان‌شناسی", "تهران", "sara"),
    ("سیر حکمت در اروپا", "محمدعلی فروغی", "فلسفه", "تهران", "reza"), ("دیوان حافظ", "حافظ", "شعر", "مشهد", "neda"),
    ("زمین سوخته", "احمد محمود", "رمان", "اهواز", "ali"), ("کوری", "ژوزه ساراماگو", "رمان", "اصفهان", "ali"),
]
COLORS = [(47, 133, 90), (43, 108, 176), (183, 121, 31), (151, 38, 109), (74, 85, 104), (192, 86, 33)]


def _cover(i):
    img = Image.new("RGB", (600, 800), COLORS[i % len(COLORS)])
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, 570, 770], outline=(255, 255, 255), width=4)
    d.ellipse([200, 260, 400, 460], outline=(255, 255, 255), width=6)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return ContentFile(buf.getvalue(), name=f"demo{i}.jpg")


class Command(BaseCommand):
    help = "داده‌ی نمونه می‌سازه (رمز همه‌ی کاربرها: demo12345)؛ چندبار اجرا بی‌خطره."

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo فقط با DEBUG=True اجرا می‌شه.")
        call_command("seed_basics", verbosity=0)
        for name in {b[3] for b in BOOKS}:
            City.objects.get_or_create(name=name)
        cities = {c.name: c for c in City.objects.all()}
        users = {}
        for name, city in USERS:
            u, created = User.objects.get_or_create(username=name, defaults={"city": cities[city], "points": 2})
            if created:
                u.set_password(PASSWORD)
                u.save()
            users[name] = u
        for i, (title, author, cat, city, owner) in enumerate(BOOKS):
            if Book.objects.filter(title=title).exists():
                continue
            b = Book(owner=users[owner], title=title, author=author, city=cities[city],
                     category=Category.objects.get(name=cat), condition="used" if i % 3 else "new",
                     description="کتاب سالم و تمیز؛ آماده‌ی مبادله.")
            b.cover.save(f"demo{i}.jpg", _cover(i), save=False)
            b.save()
        for city, name, kind in (("تهران", "ایستگاه مترو دکتر شریعتی", "metro"), ("اصفهان", "کافه کتاب سی‌وسه‌پل", "cafe"),
                                 ("تهران", "کتابخانه‌ی ملی", "library")):
            MeetingPoint.objects.get_or_create(city=cities[city], name=name, defaults={"kind": kind})
        now = timezone.now()
        Challenge.objects.get_or_create(title="این ماه ۳ کتاب بده", defaults={
            "description": "سه مبادله‌ی کامل به‌عنوان دهنده", "kind": "give", "target": 3,
            "starts_at": now - timedelta(days=5), "ends_at": now + timedelta(days=25)})
        Wishlist.objects.get_or_create(user=users["sara"], text="کلیدر")
        # یه مبادله‌ی کامل و یه مبادله‌ی در جریان
        if not Book.objects.get(title="بوف کور").exchanges.exists():
            ex = services.request_book(Book.objects.get(title="بوف کور").pk, users["ali"])
            services.accept(ex.pk, users["sara"])
            services.confirm(ex.pk, users["sara"])
            services.confirm(ex.pk, users["ali"])
            Review.objects.get_or_create(book=ex.book, user=users["ali"], defaults={"stars": 5, "text": "عالی بود."})
            ex2 = services.request_book(Book.objects.get(title="کلیدر").pk, users["sara"])
            services.accept(ex2.pk, users["neda"])
        self.stdout.write(self.style.SUCCESS(f"آماده. ورود با sara / ali / neda … و رمز {PASSWORD}"))
