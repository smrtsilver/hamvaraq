"""رگرسیون‌های فاز ۰ طرح بهبود (IMPROVEMENT_PLAN)."""

from django.db.models import ProtectedError
from django.urls import reverse

from accounts.models import User
from accounts.services import AccountError, anonymize_user
from books.models import Book
from common.tests import Base
from exchanges import services
from exchanges.models import Exchange
from trust.models import Vote


class SoftDeleteTests(Base):
    def done_exchange(self):
        ex = self.complete()
        Vote.objects.create(exchange=ex, voter=self.giver, target=self.taker, like=True)
        Vote.objects.create(exchange=ex, voter=self.taker, target=self.giver, like=True)
        return ex

    def test_book_with_completed_exchange_is_hidden_not_deleted_and_votes_survive(self):
        ex = self.done_exchange()
        book = ex.book
        self.client.login(username="taker", password="x12345678")        # صاحب فعلی کتاب
        r = self.client.post(reverse("books:delete", args=[book.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Book.all_objects.filter(pk=book.pk, deleted_at__isnull=False).exists())
        self.assertFalse(Book.objects.filter(pk=book.pk).exists())
        self.assertEqual(self.client.get(book.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("books:list")), "بوف کور")
        ex.refresh_from_db()
        self.assertEqual(ex.book.title, "بوف کور")                        # تاریخچه‌ی مبادله هنوز به کتاب وصله
        self.assertEqual(Vote.objects.count(), 2)
        self.assertEqual(ex.book.journey.count(), 1)

    def test_hard_delete_of_book_with_history_is_blocked(self):
        ex = self.done_exchange()
        with self.assertRaises(ProtectedError):
            Book.all_objects.get(pk=ex.book_id).delete()
        self.assertTrue(Exchange.objects.filter(pk=ex.pk).exists())

    def test_panel_delete_restore_and_admin_still_see_hidden_book(self):
        book = self.book()
        boss = User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        self.client.post(reverse("panel:book_delete", args=[book.pk]), {"note": "نامناسب"})
        self.assertTrue(Book.all_objects.get(pk=book.pk).is_deleted)
        self.assertContains(self.client.get("/panel/books/?status=deleted"), "حذف‌شده")
        self.assertEqual(self.client.get(f"/admin/books/book/{book.pk}/change/").status_code, 200)
        self.client.post(reverse("panel:book_restore", args=[book.pk]))
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())
        self.assertEqual(boss.pk, User.objects.get(username="boss").pk)

    def test_request_on_deleted_book_is_rejected_cleanly(self):
        book = self.book()
        book.soft_delete()
        with self.assertRaises(services.ExchangeError):
            services.request_book(book.pk, self.taker)
        with self.assertRaises(services.ExchangeError):
            services.request_book(99999, self.taker)


class AnonymizeAccountTests(Base):
    def test_deletion_anonymizes_and_keeps_others_history(self):
        ex = self.complete()
        Vote.objects.create(exchange=ex, voter=self.taker, target=self.giver, like=True)
        Vote.objects.create(exchange=ex, voter=self.giver, target=self.taker, like=True)
        self.client.login(username="giver", password="x12345678")
        self.assertEqual(self.client.post(reverse("accounts:delete"), {"password": "bad"}).status_code, 200)
        self.assertEqual(self.client.post(reverse("accounts:delete"), {"password": "x12345678"}).status_code, 302)
        self.giver.refresh_from_db()
        self.assertEqual((self.giver.username, self.giver.is_active, self.giver.has_usable_password()), (f"deleted_{self.giver.pk}", False, False))
        self.assertTrue(self.giver.is_deleted)
        self.assertEqual(Exchange.objects.count(), 1)
        self.assertEqual(Vote.objects.count(), 2)
        self.assertEqual(self.client.get(f"/accounts/u/{self.giver.username}/").status_code, 404)
        self.client.login(username="taker", password="x12345678")
        self.assertEqual(self.client.get(f"/exchanges/{ex.pk}/").status_code, 200)          # طرف مقابل هنوز مبادله رو می‌بینه

    def test_hides_books_blocks_with_active_exchange_and_protects_superuser(self):
        own = self.book(title="دست‌دوم")
        ex = services.request_book(own.pk, self.taker)
        with self.assertRaises(AccountError):
            anonymize_user(self.giver)
        services.cancel(ex.pk, self.taker)
        anonymize_user(self.giver)
        self.assertFalse(Book.objects.filter(pk=own.pk).exists())
        self.assertTrue(Book.all_objects.filter(pk=own.pk).exists())
        with self.assertRaises(AccountError):
            anonymize_user(User.objects.create_superuser("root", password="x12345678"))

    def test_user_with_history_cannot_be_hard_deleted(self):
        self.complete()
        with self.assertRaises(ProtectedError):
            self.taker.delete()


class BannedOwnerTests(Base):
    def test_banned_owner_books_are_invisible_and_unrequestable(self):
        book = self.book(title="کتاب مسدود")
        self.giver.status, self.giver.is_active = User.Status.BANNED, False
        self.giver.save()
        self.assertEqual(self.client.get(book.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("books:list")), "کتاب مسدود")
        self.assertNotContains(self.client.get(reverse("books:list"), {"q": "مسدود"}), "کتاب مسدود")
        self.assertEqual(self.client.get(reverse("books:quick"), {"q": "مسدود"}).json()["total"], 0)
        self.assertEqual(self.client.get(reverse("books:suggest"), {"q": "مسدود"}).json()["items"], [])
        self.assertNotIn(f"/books/{book.pk}/", self.client.get("/sitemap.xml").content.decode())
        with self.assertRaises(services.ExchangeError):
            services.request_book(book.pk, self.taker)
        self.assertEqual(Exchange.objects.count(), 0)

    def test_status_banned_with_active_flag_is_also_hidden(self):
        book = self.book()
        User.objects.filter(pk=self.giver.pk).update(status="banned")        # is_active هنوز True
        self.assertFalse(Book.objects.filter(pk=book.pk).exists())
        with self.assertRaises(services.ExchangeError):
            services.request_book(book.pk, self.taker)

    def test_unbanned_owner_books_return(self):
        book = self.book()
        User.objects.filter(pk=self.giver.pk).update(status="banned")
        User.objects.filter(pk=self.giver.pk).update(status="active")
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())


class InfraTests(Base):
    def test_cache_does_not_evict_throttle_counters_beyond_300_keys(self):
        from django.conf import settings
        from django.core.cache import cache
        opts = settings.CACHES["default"]["OPTIONS"]
        self.assertGreaterEqual(opts["MAX_ENTRIES"], 50000)
        self.assertEqual(opts["CULL_FREQUENCY"], 4)
        cache.clear()
        cache.set("thr:login:ip1:1", 7, 600)
        for i in range(400):
            cache.set(f"isbn:{i}", {"t": i}, 600)
        self.assertEqual(cache.get("thr:login:ip1:1"), 7)
        self.assertEqual(cache.get("isbn:0"), {"t": 0})

    def test_healthz_checks_database(self):
        from unittest import mock
        r = self.client.get("/healthz/")
        self.assertEqual((r.status_code, r.content), (200, b"ok"))
        with mock.patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor", side_effect=Exception("db gone")):
            r = self.client.get("/healthz/")
        self.assertEqual(r.status_code, 503)

    def test_debug_defaults_to_false_in_settings_source(self):
        import pathlib
        src = pathlib.Path("HamVaraqDjangoServer/settings.py").read_text(encoding="utf-8")
        self.assertIn('DEBUG = env.bool("DEBUG", default=False)', src)


class SignalWiringTests(Base):
    def test_login_signal_receiver_survives_garbage_collection(self):
        import gc
        from django.contrib.auth.signals import user_logged_in
        gc.collect()
        self.assertTrue(any(key[0] == "hv_remember_ip" for key, *_ in user_logged_in.receivers))
