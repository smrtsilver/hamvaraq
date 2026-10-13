"""فاز ۲ طرح بهبود (بخش بدون تصمیم): دفتر امتیاز، لغوکننده، یادآوری relist، ارسال پستی."""

from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from accounts.models import PointEntry, User
from common import points
from common.tests import Base
from exchanges import services
from exchanges.models import Exchange


class LedgerTests(Base):
    def setUp(self):
        points.audit(reconcile=True)               # کاربرهای Base با points مستقیم ساخته شدن؛ موجودی اولیه‌شون رو ثبت کن
        self.assertEqual(points.audit(), [])

    def entries(self, user):
        return list(PointEntry.objects.filter(user=user).order_by("id").values_list("delta", "reason", "balance_after"))

    def test_hold_refund_and_reward_are_ledgered_and_sum_matches(self):
        book = self.book()
        ex = services.request_book(book.pk, self.taker)                       # taker: ۱ → ۰
        self.assertEqual(self.entries(self.taker)[-1], (-1, "request_hold", 0))
        services.cancel(ex.pk, self.taker)
        self.assertEqual(self.entries(self.taker)[-1], (1, "request_refund", 1))
        self.complete(book)
        self.assertEqual(self.entries(self.giver)[-1], (1, "exchange_reward", 1))
        self.assertEqual([r for _, r, _ in self.entries(self.taker)][-3:], ["request_hold", "request_refund", "request_hold"])
        self.assertEqual(points.audit(), [])
        self.assertTrue(all(e.exchange_id for e in PointEntry.objects.exclude(reason__in=["opening", "reconcile"])))

    def test_rejection_expiry_and_dispute_cancel_refund_through_ledger(self):
        b1, b2 = self.book(title="الف"), self.book(title="ب")
        self.taker.points = 2
        self.taker.save()
        points.audit(reconcile=True)
        e1 = services.request_book(b1.pk, self.taker)
        services.reject(e1.pk, self.giver)
        e2 = services.request_book(b2.pk, self.taker)
        services.accept(e2.pk, self.giver)
        services.open_dispute(e2.pk, self.taker, "no_show")
        boss = User.objects.create_superuser("boss", password="x12345678")
        services.resolve_dispute(e2.pk, boss, "cancel")
        self.taker.refresh_from_db()
        self.assertEqual(self.taker.points, 2)
        self.assertEqual([r for _, r, _ in self.entries(self.taker) if r.startswith("request")], ["request_hold", "request_refund", "request_hold", "request_refund"])
        self.assertEqual(points.audit(), [])

    def test_welcome_and_panel_adjust_and_admin_edit_are_ledgered(self):
        from accounts.badges import grant_welcome
        newbie = User.objects.create_user("newbie", password="x12345678")
        self.assertEqual(grant_welcome(newbie, ""), 1)
        self.assertEqual(self.entries(newbie), [(1, "welcome", 1)])
        boss = User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        self.client.post(reverse("panel:user_action", args=[newbie.pk]), {"do": "points", "delta": "-1", "note": "جریمه"})
        newbie.refresh_from_db()
        self.assertEqual((newbie.points, self.entries(newbie)[-1][:2]), (0, (-1, "admin_adjust")))
        self.assertIn("جریمه", PointEntry.objects.filter(user=newbie).first().note)
        # ویرایش مستقیم امتیاز تو ادمین جنگو (save_model)
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().post("/admin/")
        request.user = boss
        edited = User.objects.get(pk=newbie.pk)
        edited.points = 5
        admin.site._registry[User].save_model(request, edited, None, True)
        self.assertEqual(self.entries(newbie)[-1], (5, "admin_adjust", 5))
        self.assertEqual(points.audit(), [])
        self.assertEqual(boss.pk, User.objects.get(username="boss").pk)

    def test_audit_finds_and_fixes_drift_and_command_exit_codes(self):
        User.objects.filter(pk=self.taker.pk).update(points=9)                  # دست‌کاری مستقیم دیتابیس
        self.assertEqual([b[1:] for b in points.audit()], [("taker", 9, 1)])
        from django.core.management.base import CommandError
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("check_points_ledger", stdout=out)
        call_command("check_points_ledger", "--fix", stdout=out)
        self.assertEqual(points.audit(), [])
        self.assertEqual(self.entries(self.taker)[-1], (8, "reconcile", 9))
        call_command("check_points_ledger", stdout=out)
        self.assertIn("هم‌خوانه", out.getvalue())

    def test_ledger_row_cannot_be_deleted_with_exchange_and_user_page_lists_history(self):
        from django.db.models import ProtectedError
        ex = services.request_book(self.book().pk, self.taker)
        with self.assertRaises(ProtectedError):
            ex.delete()
        self.client.login(username="taker", password="x12345678")
        page = self.client.get(reverse("accounts:points")).content.decode()
        for needle in ("نگه‌داشتن امتیاز درخواست", "اصلاح دفتر", "امتیاز من"):
            self.assertTrue(needle in page, needle)
        self.assertEqual(self.client.get(reverse("accounts:points")).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:points")).status_code, 302)

    def test_concurrent_style_double_apply_keeps_sum_consistent(self):
        for _ in range(5):
            points.apply(self.giver, 2, "admin_adjust", note="x")
        for _ in range(3):
            points.apply(self.giver.pk, -1, "admin_adjust", note="y")
        self.giver.refresh_from_db()
        self.assertEqual(self.giver.points, 0 + 10 - 3)
        self.assertEqual(points.audit(), [])
        self.assertEqual(Exchange.objects.count(), 0)


class CancelInfoTests(Base):
    def test_cancel_records_who_when_and_reason_and_notifies_with_reason(self):
        from notifications.models import Notification
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        self.client.login(username="taker", password="x12345678")
        page = self.client.get(reverse("exchanges:detail", args=[ex.pk])).content.decode()
        self.assertTrue("cancel-form" in page and "دلیل لغو" in page)
        r = self.client.post(reverse("exchanges:cancel", args=[ex.pk]), {"reason": "نتونستیم هماهنگ کنیم"})
        self.assertEqual(r.status_code, 302)
        ex.refresh_from_db()
        self.assertEqual((ex.status, ex.cancelled_by, ex.cancel_reason), ("cancelled", self.taker, "نتونستیم هماهنگ کنیم"))
        self.assertIsNotNone(ex.cancelled_at)
        self.assertTrue(Notification.objects.filter(user=self.giver, text__contains="دلیل: نتونستیم هماهنگ کنیم").exists())

    def test_reason_optional_trimmed_and_system_cancel_has_no_actor(self):
        ex = services.request_book(self.book().pk, self.taker)
        services.cancel(ex.pk, self.taker, "  " + "ا" * 400)
        ex.refresh_from_db()
        self.assertEqual(len(ex.cancel_reason), 200)
        b2 = self.book(title="دیگر")
        self.taker.points = 1
        self.taker.save()
        e2 = services.request_book(b2.pk, self.taker)
        services.auto_cancel(e2, "به‌خاطر بی‌پاسخی لغو شد")
        e2.refresh_from_db()
        self.assertEqual((e2.cancelled_by, e2.cancel_reason), (None, "سیستم: به‌خاطر بی‌پاسخی لغو شد"))

    def test_repeated_post_accept_cancellations_flag_suspicious_without_penalty(self):
        from common.stats import suspicious_accounts
        for i in range(3):
            book = self.book(title=f"ک{i}")
            self.taker.points = 1
            self.taker.save()
            ex = services.request_book(book.pk, self.taker)
            services.accept(ex.pk, self.giver)
            services.cancel(ex.pk, self.taker, "پشیمون شدم")
        flagged = {u.username: why for u, why in suspicious_accounts()}
        self.assertTrue(any("3 لغو بعد از تأیید" in w for w in flagged.get("taker", [])))
        self.taker.refresh_from_db()
        self.assertEqual((self.taker.status, self.taker.warnings), ("active", 0))             # فقط سرنخ، نه جریمه
        boss = User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        page = self.client.get(reverse("panel:user", args=[self.taker.pk])).content.decode()
        self.assertTrue("لغوهای این کاربر" in page and "بعد از تأیید" in page and "پشیمون شدم" in page)
        self.assertEqual(boss.pk, User.objects.get(username="boss").pk)


class RelistReminderTests(Base):
    def test_reminder_after_seven_days_once_only_and_not_if_relisted_or_moved(self):
        from datetime import timedelta
        from django.utils import timezone
        from books.models import Book
        from exchanges.services import process_lifecycle
        from notifications.models import Notification
        ex = self.complete()
        self.assertEqual(process_lifecycle()["relist_reminded"], 0)                         # هنوز ۷ روز نشده
        Exchange.objects.filter(pk=ex.pk).update(completed_at=timezone.now() - timedelta(days=8))
        self.assertEqual(process_lifecycle(dry_run=True)["relist_reminded"], 1)
        self.assertFalse(Notification.objects.filter(user=self.taker, text__contains="خوندی").exists())
        self.assertEqual(process_lifecycle()["relist_reminded"], 1)
        note = Notification.objects.get(user=self.taker, text__contains="خوندی")
        self.assertEqual(note.url, reverse("books:relist", args=[ex.book_id]))
        self.assertEqual(process_lifecycle()["relist_reminded"], 0)                         # فقط یک‌بار
        # کتابی که دوباره گذاشته شده یادآوری نمی‌گیره
        self.taker.points = 1
        self.taker.save()
        other = self.complete(self.book(title="دیگر"))
        Exchange.objects.filter(pk=other.pk).update(completed_at=timezone.now() - timedelta(days=9))
        Book.objects.filter(pk=other.book_id).update(status="available")
        self.assertEqual(process_lifecycle()["relist_reminded"], 0)

    def test_command_reports_relist_count(self):
        out = StringIO()
        call_command("expire_exchanges", stdout=out)
        self.assertIn("یادآوری دوباره‌گذاشتن: 0", out.getvalue())


class PostalDeliveryTests(Base):
    def setUp(self):
        self.book_obj = self.book()
        self.ex = services.request_book(self.book_obj.pk, self.taker)
        services.accept(self.ex.pk, self.giver)

    def test_owner_sets_tracking_code_requester_notified_and_sees_it(self):
        from notifications.models import Notification
        self.client.login(username="giver", password="x12345678")
        page = self.client.get(reverse("exchanges:detail", args=[self.ex.pk])).content.decode()
        self.assertTrue("postal-form" in page and "ارسال با پست" in page)
        r = self.client.post(reverse("exchanges:postal", args=[self.ex.pk]), {"tracking_code": "۱۲۳۴-۵۶۷۸ ۹۰۱۲"})
        self.assertEqual(r.status_code, 302)
        self.ex.refresh_from_db()
        self.assertEqual((self.ex.delivery, self.ex.tracking_code), ("postal", "123456789012"))
        self.assertIsNotNone(self.ex.shipped_at)
        self.assertTrue(Notification.objects.filter(user=self.taker, text__contains="کد رهگیری: 123456789012").exists())
        self.client.login(username="taker", password="x12345678")
        page = self.client.get(reverse("exchanges:detail", args=[self.ex.pk])).content.decode()
        self.assertTrue("123456789012" in page and "ارسال پستی" in page and "postal-form" not in page)

    def test_validation_and_permissions(self):
        for bad in ("", "123", "کد!خراب@@@@@@@@", "x" * 31):
            with self.assertRaises(services.ExchangeError):
                services.set_postal(self.ex.pk, self.giver, bad)
        with self.assertRaises(services.ExchangeError):
            services.set_postal(self.ex.pk, self.taker, "AB12345678")                       # فقط صاحب کتاب
        services.set_postal(self.ex.pk, self.giver, "ab-12345678")
        self.ex.refresh_from_db()
        self.assertEqual(self.ex.tracking_code, "AB12345678")
        services.set_postal(self.ex.pk, self.giver, "ZZ99999999")                           # ویرایش کد
        self.ex.refresh_from_db()
        self.assertEqual(self.ex.tracking_code, "ZZ99999999")
        services.cancel(self.ex.pk, self.taker)
        with self.assertRaises(services.ExchangeError):
            services.set_postal(self.ex.pk, self.giver, "AB12345678")                       # لغوشده

    def test_postal_exchange_still_completes_normally_and_points_move(self):
        services.set_postal(self.ex.pk, self.giver, "AB12345678")
        services.confirm(self.ex.pk, self.giver)
        services.confirm(self.ex.pk, self.taker)
        self.ex.refresh_from_db()
        self.assertEqual(self.ex.status, "completed")
        self.giver.refresh_from_db()
        self.assertEqual(self.giver.points, 1)
