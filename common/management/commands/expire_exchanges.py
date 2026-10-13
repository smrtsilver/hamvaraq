from django.core.management.base import BaseCommand

from exchanges.services import process_lifecycle


class Command(BaseCommand):
    help = "یادآوری و انقضای مبادله‌های بی‌حرکت و باز کردن اختلاف خودکار (روزانه تو cron)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="فقط بشمار، چیزی عوض نکن")

    def handle(self, *args, **opts):
        out = process_lifecycle(dry_run=opts["dry_run"])
        prefix = "(آزمایشی) " if opts["dry_run"] else ""
        self.stdout.write(f"{prefix}یادآوری: {out['reminded']}، لغو: {out['cancelled']}، اختلاف: {out['disputed']}، یادآوری دوباره‌گذاشتن: {out['relist_reminded']}")
