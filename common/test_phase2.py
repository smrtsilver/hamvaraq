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
