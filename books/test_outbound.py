"""سقف تماس‌های بیرونی هم‌زمان: وقتی همه‌ی جاها پرن، جواب سریع «شلوغه» (۵۰۳) می‌آد نه هنگ یا «پیدا نشد»، و چیزی کش منفی نمی‌شه."""

import threading
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from books import isbn as isbn_lib
from books.models import Edition

ISBN = "9786229015155"


class OutboundSlotTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(User.objects.create_user("reader", password="x-strong-pass-1"))
        # هیچ جای خالی‌ای نیست و صبر کوتاهه
        patches = [mock.patch.object(isbn_lib, "_SLOTS", threading.BoundedSemaphore(1)), mock.patch.object(isbn_lib, "SLOT_WAIT", 0.01)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        isbn_lib._SLOTS.acquire()
        self.addCleanup(isbn_lib._SLOTS.release)

    def test_isbn_lookup_says_busy_and_caches_nothing(self):
        with mock.patch.object(isbn_lib, "_lookup_sources") as sources:
            r = self.client.get(reverse("books:isbn"), {"isbn": ISBN})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"], "busy")
        sources.assert_not_called()
        self.assertIsNone(cache.get(f"isbn2:{ISBN}"))

    def test_cached_and_stored_results_skip_the_gate(self):
        cache.set(f"isbn2:{ISBN}", {"title": "اسب سیاه"}, 60)
        self.assertEqual(isbn_lib.lookup_full(ISBN)["title"], "اسب سیاه")
        Edition.objects.create(isbn13="9786227992571", title="بادام", source="opac", confidence=90)
        self.assertEqual(self.client.get(reverse("books:isbn"), {"isbn": "9786227992571"}).status_code, 200)

    def test_title_search_says_busy(self):
        with mock.patch.object(isbn_lib, "_get") as get:
            r = self.client.get(reverse("books:catalog_search"), {"q": "اسب سیاه"})
        self.assertEqual((r.status_code, r.json()["error"]), (503, "busy"))
        get.assert_not_called()

    def test_cover_busy_is_not_negatively_cached(self):
        Edition.objects.create(isbn13="9786227992571", title="بادام", source="ketab", confidence=90,
                               cover_url="https://pic.ketab.ir/DataBase/BookImages/01/1.jpg")
        with mock.patch("urllib.request.urlopen") as urlopen:
            r = self.client.get(reverse("books:cover_image", args=["9786227992571"]))
        self.assertEqual(r.status_code, 503)
        urlopen.assert_not_called()
        self.assertIsNone(cache.get("cover-img:9786227992571"))

    def test_slot_is_released_after_lookup(self):
        isbn_lib._SLOTS.release()
        with mock.patch.object(isbn_lib, "_lookup_sources", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                isbn_lib.lookup_full(ISBN)
        self.assertTrue(isbn_lib._SLOTS.acquire(timeout=0))   # خطا هم جا رو آزاد کرده
