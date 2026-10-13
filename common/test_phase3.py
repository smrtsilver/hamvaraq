from io import StringIO

"""فاز ۳ طرح بهبود: لیست، کارت، جزئیات، فرم، تصویر، دسترس‌پذیری."""

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from books.models import Book
from common.tests import Base, make_city
from exchanges import services
from trust.models import Vote


class BookListTests(Base):
    def titles(self, **params):
        r = self.client.get(reverse("books:list"), params)
        return [b.title for b in r.context["page"]], r

    def test_default_shows_only_available_and_all_flag_adds_reserved_never_exchanged(self):
        self.book(title="موجود")
        reserved = self.book(title="رزرو")
        Book.objects.filter(pk=reserved.pk).update(status="reserved")
        done = self.book(title="تمام")
        Book.objects.filter(pk=done.pk).update(status="exchanged")
        self.assertEqual(self.titles()[0], ["موجود"])
        self.assertEqual(set(self.titles(all="on")[0]), {"موجود", "رزرو"})

    def test_sort_new_near_and_wanted(self):
        shiraz = make_city("شیراز")
        a = self.book(title="الف")                                        # اصفهان
        b = Book.objects.create(owner=self.giver, title="ب", author="ن", city=self.tehran)
        c = Book.objects.create(owner=self.giver, title="ج", author="ن", city=shiraz)
        self.assertEqual(self.titles(sort="new")[0], ["ج", "ب", "الف"])
        self.client.login(username="taker", password="x12345678")        # taker تهران
        self.assertEqual(self.titles(sort="near")[0][0], "ب")             # هم‌شهری اول
        third = User.objects.create_user("t3", password="x12345678", points=2)
        fourth = User.objects.create_user("t4", password="x12345678", points=2)
        services.request_book(a.pk, third)
        services.request_book(a.pk, fourth)
        services.request_book(c.pk, third)
        self.assertEqual(self.titles(sort="wanted")[0][:2], ["الف", "ج"])
        self.client.logout()
        self.assertEqual(self.titles(sort="near")[0], ["ج", "ب", "الف"])  # مهمان: مثل جدیدترین
        self.assertEqual(b.pk, Book.objects.get(title="ب").pk)

    def test_active_filter_chips_remove_one_filter_only(self):
        self.book()
        r = self.client.get(reverse("books:list"), {"q": "بوف", "condition": "used", "sort": "wanted"})
        chips = dict(r.context["chips"])
        self.assertEqual(set(chips), {"«بوف»", "دست‌دوم", "پرتقاضاترین"})
        self.assertTrue(chips["«بوف»"] in ("?condition=used&sort=wanted", "?sort=wanted&condition=used"))
        self.assertTrue("q=" not in chips["«بوف»"])
        self.assertEqual(self.client.get(reverse("books:list")).context["chips"], [])
        self.assertContains(r, "پاک کردن همه")

    def test_card_badges_distance_hot_and_trusted_without_n_plus_one(self):
        local = Book.objects.create(owner=self.giver, title="محلی", author="ن", city=self.tehran)
        self.book(title="دور")
        taker2 = User.objects.create_user("t2", password="x12345678", points=3, city=self.tehran)
        t3 = User.objects.create_user("t3", password="x12345678", points=3)
        services.request_book(local.pk, taker2)
        services.request_book(local.pk, t3)                               # دو درخواست ← پرتقاضا
        self.client.login(username="taker", password="x12345678")
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(reverse("books:list"))
        books = {b.title: b for b in r.context["page"]}
        self.assertEqual((books["محلی"].distance, books["محلی"].hot), ("هم‌شهری", True))
        self.assertEqual((books["دور"].distance, books["دور"].hot), ("", False))
        self.assertContains(r, "پرتقاضا")
        self.assertLess(len(ctx), 25)

    def test_trusted_badge_needs_votes_and_percent(self):
        from books.listing import decorate_cards
        book = self.book()
        for i, like in enumerate((True, True, True)):
            voter = User.objects.create_user(f"vv{i}", password="x12345678")
            from exchanges.models import Exchange
            e = Exchange.objects.create(book=book, requester=voter, owner=self.giver, status="completed")
            Vote.objects.create(exchange=e, voter=voter, target=self.giver, like=like)
        self.assertTrue(decorate_cards([Book.objects.get(pk=book.pk)])[0].trusted)
        v = Vote.objects.first()
        Vote.objects.filter(pk=v.pk).update(like=False)
        self.assertFalse(decorate_cards([Book.objects.get(pk=book.pk)])[0].trusted)     # ۶۷٪ < ۹۰٪

    def test_save_search_button_only_when_wishlist_enabled_and_query_present(self):
        self.client.login(username="taker", password="x12345678")
        self.assertNotContains(self.client.get(reverse("books:list"), {"q": "بوف"}), "این جستجو رو به لیست آرزو")
        with override_settings(WISHLIST_ENABLED=True):
            self.assertContains(self.client.get(reverse("books:list"), {"q": "بوف"}), "این جستجو رو به لیست آرزو")
            self.assertNotContains(self.client.get(reverse("books:list")), "این جستجو رو به لیست آرزو")


class BookDetailTests(Base):
    def test_request_cta_hold_note_fixed_bar_share_and_owner_books(self):
        book = self.book(title="کتاب اصلی")
        self.book(title="کتاب دوم")
        self.client.login(username="taker", password="x12345678")        # taker یک امتیاز دارد
        page = self.client.get(book.get_absolute_url()).content.decode()
        self.assertEqual(page.count("درخواست کتاب (۱ امتیاز)"), 2)        # ستون اصلی + نوار ثابت موبایل
        for needle in ('class="cta-fixed"', "cta-bar has-fixed", "چطور نگه داشته می‌شه", "data-share", "کتاب‌های دیگر giver", "کتاب دوم"):
            self.assertTrue(needle in page, needle)

    def test_no_points_blocked_and_owner_and_unavailable_views_render(self):
        book = self.book()
        User.objects.create_user("poor", password="x12345678")
        self.client.login(username="poor", password="x12345678")
        page = self.client.get(book.get_absolute_url()).content.decode()
        self.assertTrue("امتیاز نداری" in page and "چطور نگه داشته می‌شه" not in page)
        self.client.login(username="giver", password="x12345678")
        owner_page = self.client.get(book.get_absolute_url()).content.decode()
        self.assertTrue("cta-fixed" not in owner_page and "کیفیت آگهی:" in owner_page)
        Book.objects.filter(pk=book.pk).update(status="reserved")
        self.client.login(username="taker", password="x12345678")
        self.assertTrue("درخواست یه نفر دیگه رو قبول کرده" in self.client.get(book.get_absolute_url()).content.decode())
        self.client.logout()
        Book.objects.filter(pk=book.pk).update(status="available")
        guest = self.client.get(book.get_absolute_url()).content.decode()
        self.assertTrue("برای درخواست وارد شو" in guest)


class CoverImageTests(Base):
    def make_book(self, w=900, h=1200):
        import io
        from django.core.files.base import ContentFile
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (180, 60, 60)).save(buf, "JPEG")
        book = Book(owner=self.giver, title="با جلد", author="ن", city=self.tehran, cover=ContentFile(buf.getvalue(), name="c.jpg"))
        book.save()
        return Book.objects.get(pk=book.pk)

    def test_upload_builds_webp_variants_dimensions_and_lqip(self):
        from PIL import Image
        b = self.make_book()
        self.assertEqual((b.cover_w, b.cover_h), (900, 1200))
        self.assertTrue(b.cover_lqip.startswith("data:image/jpeg;base64,") and len(b.cover_lqip) < 900)
        with Image.open(b.cover_webp.path) as big, Image.open(b.cover_thumb_webp.path) as small:
            self.assertEqual((big.format, small.format), ("WEBP", "WEBP"))
            self.assertEqual((max(big.size), max(small.size)), (960, 420))
        self.assertLess(b.cover_thumb_webp.size, b.cover_thumb.size)           # WebP کوچک‌تر از JPEG هم‌اندازه

    def test_picture_tag_has_srcset_dimensions_and_only_first_gets_high_priority(self):
        b = self.make_book()
        self.make_book()
        page = self.client.get(reverse("books:list")).content.decode()
        self.assertEqual(page.count('fetchpriority="high"'), 1)                # فقط اولین کارت
        self.assertTrue(page.count("loading=\"lazy\"") >= 1)
        for needle in ('<picture><source type="image/webp"', "420w", "960w", 'width="315" height="420"', 'decoding="async"', "data-lqip="):
            self.assertTrue(needle in page, needle)
        detail = self.client.get(b.get_absolute_url()).content.decode()
        self.assertEqual(detail.count('fetchpriority="high"'), 1)
        self.assertTrue('width="720" height="960"' in detail and "data-gallery-main" in detail)

    def test_no_cover_means_no_picture_and_removal_clears_variants(self):
        b = self.make_book()
        b.cover = ""
        b.save()
        b.refresh_from_db()
        self.assertEqual((b.cover_webp.name, b.cover_thumb_webp.name, b.cover_w, b.cover_lqip), ("", "", None, ""))

    def test_generate_image_variants_backfills_old_books(self):
        from django.core.management import call_command
        b = self.make_book()
        Book.all_objects.filter(pk=b.pk).update(cover_webp="", cover_thumb_webp="", cover_w=None, cover_h=None, cover_lqip="")
        out = StringIO()
        call_command("generate_image_variants", stdout=out)
        b.refresh_from_db()
        self.assertTrue(b.cover_webp and b.cover_thumb_webp and b.cover_w == 900 and b.cover_lqip)
        self.assertIn("ساخته‌شده: 1", out.getvalue())
        call_command("generate_image_variants", stdout=out)
        self.assertIn("ساخته‌شده: 0", out.getvalue().splitlines()[-1])

    def test_broken_image_does_not_block_book_save(self):
        from unittest import mock
        with mock.patch("common.images.make_webp", side_effect=ValueError("bad")):
            b = self.make_book()
        self.assertTrue(b.cover)
        self.assertEqual(b.cover_webp.name, "")


class FormUxTests(Base):
    def test_book_form_loads_stepper_compress_scan_and_preview(self):
        self.client.login(username="giver", password="x12345678")
        page = self.client.get(reverse("books:create")).content.decode()
        for needle in ("data-stepper", "js/stepper.js", "js/compress.js", "js/scan.js", "js/preview.js", "data-scan-target"):
            self.assertTrue(needle in page, needle)
        self.assertTrue('<h3>' not in page.split("form-layout")[1].split("</form>")[0])      # سرتیترها h2 (ترتیب درست heading)
        posts = self.client.get(reverse("posts:create")).content.decode()
        self.assertTrue("js/compress.js" in posts)
