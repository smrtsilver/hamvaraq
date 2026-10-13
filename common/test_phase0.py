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


class IsbnBudgetTests(Base):
    """استعلام شابک: موازی، بودجه‌ی زمانی، منبع کند، و circuit breaker."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.addCleanup(cache.clear)

    def slow(self, seconds, result=None):
        import time

        def source(isbn, timeout):
            time.sleep(seconds)
            return result
        return source

    def patch_sources(self, nlai=None, ol=None, google=None):
        from unittest import mock
        from books import isbn
        noop = self.slow(0)
        return (mock.patch.object(isbn, "_nlai", nlai or noop), mock.patch.object(isbn, "_open_library", ol or noop),
                mock.patch.object(isbn, "_google", google or noop))

    def run_patched(self, nlai=None, ol=None, google=None, **kw):
        import contextlib
        import time
        from books import isbn
        with contextlib.ExitStack() as stack:
            for p in self.patch_sources(nlai, ol, google):
                stack.enter_context(p)
            start = time.monotonic()
            result = isbn.lookup(kw.pop("isbn", "9786007547717"), **kw)
            return result, time.monotonic() - start

    def test_slow_sources_do_not_hold_the_request_beyond_budget(self):
        hang = self.slow(4)
        result, took = self.run_patched(nlai=hang, ol=hang, google=hang, timeout=0.5)
        self.assertIsNone(result)
        self.assertLess(took, 1.2)
        from django.core.cache import cache
        self.assertIsNone(cache.get("isbn2:9786007547717"))                     # timeout نتیجه‌ی منفیِ قطعی نیست

    def test_two_back_to_back_slow_lookups_and_site_stays_responsive(self):
        import time
        hang = self.slow(3)
        r1, t1 = self.run_patched(nlai=hang, ol=hang, google=hang, timeout=0.4, isbn="9786007547717")
        r2, t2 = self.run_patched(nlai=hang, ol=hang, google=hang, timeout=0.4, isbn="9789643051099")
        self.assertEqual((r1, r2), (None, None))
        self.assertLess(t1 + t2, 1.5)
        start = time.monotonic()
        self.assertEqual(self.client.get("/healthz/").status_code, 200)         # thread‌های معطل سایت رو نگرفتن
        self.assertLess(time.monotonic() - start, 0.5)

    def test_priority_nlai_wins_even_if_google_is_faster_and_fast_exit(self):
        nlai = lambda isbn, timeout: (__import__("time").sleep(0.15), {"isbn": isbn, "title": "ملی", "author": "الف"})[1]   # noqa: E731
        google = lambda isbn, timeout: {"isbn": isbn, "title": "گوگل", "author": "ب"}                                          # noqa: E731
        result, took = self.run_patched(nlai=nlai, google=google, timeout=2)
        self.assertEqual(result["title"], "ملی")
        self.assertLess(took, 1.0)
        # اگه منبع مهم‌تر جوابی نداره، منبع بعدی گرفته می‌شه بدون اینکه کل بودجه صبر کنه
        result, took = self.run_patched(ol=lambda isbn, timeout: {"isbn": isbn, "title": "اپن", "author": "ج"}, timeout=2, isbn="9789643051099")
        self.assertEqual(result["title"], "اپن")
        self.assertLess(took, 1.0)

    def test_breaker_opens_after_three_failures_and_skips_the_source(self):
        from books import isbn
        calls = []

        def broken(isbn_, timeout):
            calls.append(1)
            raise OSError("down")
        for valid in ("9786007547717", "9780140328721", "9780306406157"):
            self.run_patched(ol=broken, isbn=valid)
        self.assertTrue(isbn.breaker_open("openlibrary"))
        n = len(calls)
        self.run_patched(ol=broken, isbn="9789643051099")
        self.assertEqual(len(calls), n)                                           # دیگه صدا زده نمی‌شه
        self.assertFalse(isbn.breaker_open("nlai"))
        isbn.breaker_record("openlibrary", True)                                  # موفقیت بازش می‌گردونه
        self.assertFalse(isbn.breaker_open("openlibrary"))

    def test_negative_result_cached_only_when_all_sources_answered(self):
        from django.core.cache import cache
        self.run_patched(isbn="9789643051099")
        self.assertEqual(cache.get("isbn2:9789643051099"), {})
        self.run_patched(ol=lambda i, t: (_ for _ in ()).throw(OSError()), isbn="9780140328721")
        self.assertIsNone(cache.get("isbn2:9780140328721"))

    def test_entrypoint_uses_gthread_and_budget_setting_exists(self):
        import pathlib
        from django.conf import settings
        src = pathlib.Path("docker/entrypoint.prod.sh").read_text(encoding="utf-8")
        self.assertIn("--worker-class gthread", src)
        self.assertEqual(settings.ISBN_BUDGET, 3.0)


class CardCacheTests(Base):
    def setUp(self):
        import shutil
        from django.conf import settings
        from pathlib import Path
        self.book_obj = self.book(title="بوف کور")
        self.addCleanup(lambda: shutil.rmtree(Path(settings.MEDIA_ROOT) / "cards", ignore_errors=True))

    def get(self, **kw):
        return self.client.get(reverse("books:card", args=[self.book_obj.pk]), **kw)

    def test_second_request_is_served_from_disk_without_rendering(self):
        from unittest import mock
        from books import card
        with mock.patch.object(card, "render_card", wraps=card.render_card) as render:
            r1 = self.get()
            body1 = b"".join(r1.streaming_content)
            r2 = self.get()
            body2 = b"".join(r2.streaming_content)
        self.assertEqual((r1.status_code, r1["Content-Type"]), (200, "image/png"))
        self.assertEqual(render.call_count, 1)
        self.assertEqual(body1, body2)
        self.assertTrue(body1.startswith(b"\x89PNG"))

    def test_content_change_creates_new_version_and_removes_old_file(self):
        from books import card
        self.get()
        old = card.cached_card_path(self.book_obj)
        self.assertTrue(old.exists())
        self.book_obj.title = "بوف کور (چاپ تازه)"
        self.book_obj.save()
        self.get()
        new = card.cached_card_path(self.book_obj)
        self.assertNotEqual(old.name, new.name)
        self.assertTrue(new.exists())
        self.assertFalse(old.exists())

    def test_etag_304_download_header_and_hidden_book_404(self):
        r = self.get()
        etag = r["ETag"]
        self.assertEqual(self.get(HTTP_IF_NONE_MATCH=etag).status_code, 304)
        self.assertIn("attachment", self.client.get(reverse("books:card", args=[self.book_obj.pk]), {"download": 1})["Content-Disposition"])
        self.book_obj.soft_delete()
        self.assertEqual(self.get().status_code, 404)

    def test_x_accel_redirect_mode_sends_header_only(self):
        from django.test import override_settings
        with override_settings(CARD_X_ACCEL_PREFIX="/_cards/"):
            r = self.get()
        self.assertEqual(r.content, b"")
        self.assertRegex(r["X-Accel-Redirect"], rf"^/_cards/{self.book_obj.pk}-[0-9a-f]{{12}}\.png$")

    def test_render_rate_limited_only_on_cache_miss(self):
        from unittest import mock
        self.get()                                           # کش می‌شه
        with mock.patch("common.throttle.hit", return_value=False):
            self.assertEqual(self.get().status_code, 200)     # از کش: بدون شمارش نرخ
            other = self.book(title="کتاب دیگر")
            r = self.client.get(reverse("books:card", args=[other.pk]))
        self.assertEqual(r.status_code, 429)


class WishlistMatchingTests(Base):
    def setUp(self):
        from django.test import override_settings
        patcher = override_settings(WISHLIST_ENABLED=True)
        patcher.enable()
        self.addCleanup(patcher.disable)

    def wish(self, text, user=None):
        from books.services import add_wish
        return add_wish(user or self.taker, text)

    def notes(self):
        from notifications.models import Notification
        return Notification.objects.filter(user=self.taker, kind="wishlist").count()

    def new_book(self, title, author="هدایت", **kw):
        from books.services import notify_wishlists
        b = Book.objects.create(owner=self.giver, title=title, author=author, city=self.isfahan, category=self.cat, **kw)
        notify_wishlists(b)
        return b

    def test_short_and_stopword_wishes_are_rejected_and_never_match(self):
        for bad in ("ا", "کتاب", "رمان", "از", "  ", "کتاب رمان"):
            wish, error = self.wish(bad)
            self.assertIsNone(wish, bad)
            self.assertIn("کلمه", error)
        from books.models import Wishlist
        legacy = Wishlist.objects.create(user=self.taker, text="کتاب")        # آرزوی قدیمی/مستقیم: توکن ندارد
        self.assertEqual(legacy.tokens.count(), 0)
        self.new_book("کتاب مفید")
        self.new_book("ا")
        self.assertEqual(self.notes(), 0)

    def test_whole_word_match_not_substring(self):
        self.wish("بوف")
        self.new_book("بوفه‌ی مدرن")                                         # زیررشته‌ی «بوف» ولی کلمه‌ی دیگر
        self.assertEqual(self.notes(), 0)
        self.new_book("بوف کور")
        self.assertEqual(self.notes(), 1)

    def test_all_words_required_and_author_counts(self):
        self.wish("بوف کور هدایت")
        self.new_book("بوف کور", author="نویسنده‌ی دیگر")                   # «هدایت» نیست
        self.assertEqual(self.notes(), 0)
        self.new_book("بوف کور", author="صادق هدایت")
        self.assertEqual(self.notes(), 1)

    def test_isbn_wish_matches_exact_isbn_only_and_one_note_per_user(self):
        self.wish("978-964-305-109-2")
        self.wish("کلیدر")
        self.new_book("عنوان دیگر", isbn="9780000000002")
        self.assertEqual(self.notes(), 0)
        b = self.new_book("کلیدر جلد اول", isbn="9789643051092")              # هم شابک هم عنوان؛ فقط یک اعلان
        self.assertEqual(self.notes(), 1)
        self.assertEqual(b.owner, self.giver)

    def test_owner_not_notified_and_persian_variants_match(self):
        from books.services import notify_wishlists
        self.wish("كلیدر", user=self.giver)                                  # ک عربی
        mine = Book.objects.create(owner=self.giver, title="کلیدر", author="دولت‌آبادی", city=self.isfahan)
        notify_wishlists(mine)
        from notifications.models import Notification
        self.assertEqual(Notification.objects.filter(user=self.giver, kind="wishlist").count(), 0)
        self.wish("كلیدر")                                                   # taker
        self.new_book("کلیدر", author="دولت‌آبادی")
        self.assertEqual(self.notes(), 1)

    def test_matching_uses_indexed_token_query_not_full_scan_and_limits(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from books.models import Wishlist
        for i in range(20):
            self.wish(f"عنوان{i}ی منحصر")
        self.wish("بوف")
        b = Book.objects.create(owner=self.giver, title="بوف کور", author="هدایت", city=self.isfahan)
        from books.services import matching_wishes
        with CaptureQueriesContext(connection) as ctx:
            result = list(matching_wishes(b))
        self.assertEqual([w.text for w in result], ["بوف"])
        self.assertLessEqual(len(ctx), 4)
        self.assertEqual(Wishlist.objects.filter(user=self.taker).count(), 21)
        # سقف تعداد آرزو
        for i in range(Wishlist.MAX_PER_USER - 21):
            self.wish(f"سقف{i}ام اضافه")
        wish, error = self.wish("یکی بیشتر از حد")
        self.assertIsNone(wish)
        self.assertIn("حداکثر", error)

    def test_view_shows_error_for_junk_wish(self):
        from books.models import Wishlist
        self.client.login(username="taker", password="x12345678")
        r = self.client.post("/books/wishlist/", {"text": "کتاب"}, follow=True)
        self.assertContains(r, "حداقل یه کلمه")
        self.assertEqual(Wishlist.objects.count(), 0)
        self.client.post("/books/wishlist/", {"text": "بوف کور"})
        self.assertEqual(Wishlist.objects.count(), 1)
