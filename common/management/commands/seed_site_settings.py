from django.core.management.base import BaseCommand

from common.models import SiteSetting


class Command(BaseCommand):
    help = "رکورد تنظیمات سایت رو با مقدارهای پیش‌فرض می‌سازه (اگه نباشه)"

    def handle(self, *args, **opts):
        _, created = SiteSetting.objects.get_or_create(pk=1)
        self.stdout.write(self.style.SUCCESS("ساخته شد." if created else "از قبل بود."))
