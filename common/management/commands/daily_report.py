from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from common.stats import collect


class Command(BaseCommand):
    help = "گزارش روزانه‌ی وضعیت سایت؛ با --email به ADMIN_EMAILS هم می‌فرسته (برای cron)"

    def add_arguments(self, parser):
        parser.add_argument("--email", action="store_true")

    def handle(self, *args, **opts):
        s = collect()
        st = s["exchanges"]["by_status"]
        lines = [
            f"کاربر: {s['users']['total']} (جدید ۷ روز: {s['users']['new7']}، محدود: {s['users']['restricted']}، مسدود: {s['users']['banned']})",
            f"کتاب: موجود {s['books']['available']}، رزرو {s['books']['reserved']}، مبادله‌شده {s['books']['exchanged']}، جدید ۷ روز {s['books']['new7']}",
            f"مبادله: تکمیل ۷ روز {s['exchanges']['completed7']}، ۳۰ روز {s['exchanges']['completed30']}؛ "
            f"درخواست {st.get('requested', 0)}، تأییدشده {st.get('accepted', 0)}",
            f"گیرکرده: درخواست‌های بی‌پاسخ {s['exchanges']['stale_requested']}، تأییدشده‌های معلق {s['exchanges']['stale_accepted']}",
            f"اختلاف باز: {s['exchanges']['disputed']}",
            f"صف تأیید: معرفی {s['queues']['posts']}، اطلاعیه {s['queues']['announcements']}",
            f"گزارش باز: {s['reports']['open']}، در بررسی: {s['reports']['reviewing']}"
            + (f" (قدیمی‌ترین {s['reports']['oldest_days']} روزه)" if s["reports"]["oldest_days"] is not None else ""),
            f"حساب مشکوک: {len(s['suspicious'])}",
        ]
        lines += [f"  - {u.username}: {'؛ '.join(why)}" for u, why in s["suspicious"]]
        body = "\n".join(lines)
        self.stdout.write(body)
        if opts["email"]:
            if not settings.ADMIN_EMAILS:
                self.stderr.write("ADMIN_EMAILS خالیه؛ ایمیلی فرستاده نشد.")
                return
            send_mail("گزارش روزانه‌ی هم‌ورق", body, None, settings.ADMIN_EMAILS)
