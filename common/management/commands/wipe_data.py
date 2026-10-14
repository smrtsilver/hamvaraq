"""
پاک کردن همه‌ی داده‌های ساخته‌شده (کاربرها، کتاب‌ها، مبادله‌ها، پیام‌ها، اعلان‌ها، پست‌ها، آمار…) و فایل‌های media،
برای شروع تمیز بعد از دوره‌ی تست.

می‌مونه: استان‌ها، شهرها، دسته‌ها، تنظیمات سایت، و جدول‌های خود جنگو (migration، دسترسی‌ها، گروه‌ها).
قبل از پاک کردن به‌طور پیش‌فرض بکاپ کامل (دیتابیس + media) با backup_db گرفته می‌شه.

اجرا:
    python manage.py wipe_data                 # می‌پرسه و تأیید می‌خواد
    python manage.py wipe_data --yes           # بدون پرسیدن (برای اسکریپت)
    python manage.py wipe_data --no-backup     # بدون بکاپ (توصیه نمی‌شه)
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction

KEEP_TABLES = {
    "django_migrations",
    "django_content_type",
    "auth_permission",
    "auth_group",
    "auth_group_permissions",
    "common_province",
    "common_city",
    "common_sitesetting",
    "books_category",
}
CONFIRM_WORD = "پاک"


class Command(BaseCommand):
    help = "همه‌ی داده‌های کاربرها و فایل‌های media رو پاک می‌کنه (شهرها، دسته‌ها و تنظیمات سایت می‌مونن)"

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="بدون پرسیدن تأیید")
        parser.add_argument("--no-backup", action="store_true", help="قبلش بکاپ نگیره")

    def handle(self, *args, **opts):
        tables = sorted(set(connection.introspection.django_table_names(only_existing=True)) - KEEP_TABLES)

        if not opts["yes"]:
            self.stdout.write(self.style.WARNING(
                f"{len(tables)} جدول و همه‌ی فایل‌های {settings.MEDIA_ROOT} پاک می‌شن (همه‌ی کاربرها هم)."
            ))
            if input(f"برای ادامه بنویس «{CONFIRM_WORD}»: ").strip() != CONFIRM_WORD:
                raise CommandError("لغو شد؛ چیزی پاک نشد.")

        if not opts["no_backup"]:
            call_command("backup_db", media=True, stdout=self.stdout)

        # TRUNCATE همه با هم (پستگرس) یا DELETE (SQLite) و ریست شمارنده‌ها؛ همون کاری که flush می‌کنه
        # ولی جدول‌های مرجع رو نگه می‌داره. اگه جدول نگه‌داشته‌ای به جدول پاک‌شونده FK داشته باشه خطا می‌ده و
        # هیچ‌چیز پاک نمی‌شه.
        sql = connection.ops.sql_flush(no_style(), tables, reset_sequences=True, allow_cascade=False)
        with transaction.atomic():
            connection.ops.execute_sql_flush(sql)

        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists():
            for child in media_root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()

        cache.clear()
        call_command("seed_basics", verbosity=0)
        self.stdout.write(self.style.SUCCESS(
            f"{len(tables)} جدول و فایل‌های media پاک شدن. حالا با createsuperuser یه مدیر بساز."
        ))
