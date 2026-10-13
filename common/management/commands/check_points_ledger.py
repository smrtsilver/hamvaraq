from django.core.management.base import BaseCommand, CommandError

from common import points


class Command(BaseCommand):
    help = "مجموع دفتر امتیاز با User.points مقایسه می‌شه؛ خروجی غیرصفر یعنی ناهمخوانی (برای cron/مانیتور). --fix ردیف «اصلاح دفتر» می‌زنه."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true")

    def handle(self, *args, **opts):
        bad = points.audit(reconcile=opts["fix"])
        for pk, name, current, ledger in bad:
            self.stdout.write(f"✗ {name} (#{pk}): امتیاز {current} ولی دفتر {ledger}")
        if bad and not opts["fix"]:
            raise CommandError(f"{len(bad)} حساب ناهمخوان؛ با --fix اصلاح می‌شه (علت رو هم بررسی کن).")
        self.stdout.write(self.style.SUCCESS("دفتر امتیاز با همه‌ی حساب‌ها هم‌خوانه." if not bad else f"{len(bad)} حساب اصلاح شد."))
