from django.core.management.base import BaseCommand, CommandError

from common.locations import DATA_PATH, load_locations
from common.models import City, Province


def _key(text):
    return "".join(str(text).replace("‌", "").split())


class Command(BaseCommand):
    help = (
        "استان‌ها و شهرهای ایران رو از common/data/iran_locations.json (پاک‌سازی‌شده) می‌سازه. "
        "چندبار اجرا بی‌خطره؛ فقط موارد جدید اضافه می‌شن و شهرهای موجود (حتی با املای کمی متفاوت) تکرار نمی‌شن."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DATA_PATH), help="مسیر فایل JSON با ساختار {استان: [شهرها]}")

    def handle(self, *args, **opts):
        try:
            data = load_locations(opts["file"])
        except FileNotFoundError as exc:
            raise CommandError(f"فایل پیدا نشد: {opts['file']}") from exc
        except ValueError as exc:
            raise CommandError(f"فایل JSON معتبر نیست: {exc}") from exc

        new_provinces = new_cities = 0
        for province_name, cities in data.items():
            province, created = Province.objects.get_or_create(name=province_name)
            new_provinces += created
            existing = {_key(n) for n in province.cities.values_list("name", flat=True)}
            fresh = [City(province=province, name=n) for n in cities if _key(n) not in existing]
            City.objects.bulk_create(fresh)
            new_cities += len(fresh)
        self.stdout.write(self.style.SUCCESS(
            f"{new_provinces} استان و {new_cities} شهر جدید (کل: {Province.objects.count()} استان، {City.objects.count()} شهر)."))
