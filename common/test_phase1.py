"""فاز ۱ طرح بهبود: کاتالوگ چاپ‌ها (Edition) و خط‌لوله‌ی شابک."""

from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.models import User
from books import catalog, isbn
from books.models import Book, Edition
from common.tests import Base

NLAI_REC = {"isbn": "9786007547717", "title": "مدارس دوست‌داشتنی", "authors": ["کبری صابر"], "publisher": "نشر نمونه", "year": 1392, "year_calendar": "jalali", "pages": 120}
OL_REC = {"isbn": "9786007547717", "title": "مدارس دوست داشتنی", "authors": ["Kobra Saber"], "cover_url": "https://covers.example/1.jpg"}
GOOGLE_REC = {"isbn": "9786007547717", "title": "مدارس دوست‌داشتنی", "authors": ["صابر"], "publisher": "گوگل‌ناشر", "cover_url": "https://g.example/2.jpg"}


class NormalizationTests(Base):
    def test_check_digits_conversion_and_persian_digits(self):
        self.assertEqual(isbn.normalize_isbn("978-964-6194-48-9"), "9789646194489")
        self.assertEqual(isbn.normalize_isbn("۹۷۸-۹۶۴-۶۱۹۴-۴۸-۹"), "9789646194489")
        self.assertEqual(isbn.normalize_isbn("٩٧٨٩٦٤٦١٩٤٤٨٩"), "9789646194489")           # ارقام عربی
        self.assertEqual(isbn.normalize_isbn("0-306-40615-2"), "9780306406157")
        self.assertEqual(isbn.normalize_isbn("0306406152"), isbn.normalize_isbn("9780306406157"))   # ۱۰ و ۱۳ یکی
        self.assertEqual(isbn.normalize_isbn("080442957X"), "9780804429573")                # رقم کنترل X
        self.assertEqual(isbn.normalize_isbn("080442957x"), "9780804429573")
        for bad in ("9789646194485", "0306406153", "123", "abc", "", None, "97896461944890"):
            self.assertIsNone(isbn.normalize_isbn(bad), bad)

    def test_error_messages_distinguish_checksum_from_length(self):
        self.assertIn("رقم کنترل", isbn.isbn_error("9789646194485"))
        self.assertIn("۱۰ یا ۱۳", isbn.isbn_error("123"))
        self.assertIsNone(isbn.isbn_error("9789646194489"))
        self.assertIsNone(isbn.isbn_error(""))

    def test_book_form_and_bulk_reject_bad_checksum_and_store_isbn13(self):
        from books.forms import BookForm
        base = {"title": "ب", "author": "ن", "condition": "used", "city": self.tehran.pk}
        bad = BookForm({**base, "isbn": "978-964-6194-48-5"}, default_city=self.tehran)
        self.assertFalse(bad.is_valid())
        self.assertIn("رقم کنترل", bad.errors["isbn"][0])
        ok = BookForm({**base, "isbn": "0-306-40615-2"}, default_city=self.tehran)
        self.assertTrue(ok.is_valid(), ok.errors)
        self.assertEqual(ok.cleaned_data["isbn"], "9780306406157")


class MergeAndConfidenceTests(Base):
    def test_single_source_is_40_and_priority_per_field(self):
        m = isbn.merge_records({"openlibrary": {"isbn": "x", "title": "T", "authors": ["A"]}})
        self.assertEqual((m["confidence"], m["sources"], m["author"]), (40, ["openlibrary"], "A"))
        m = isbn.merge_records({"nlai": NLAI_REC, "openlibrary": OL_REC, "google": GOOGLE_REC})
        self.assertEqual(m["title"], "مدارس دوست‌داشتنی")                 # فارسی: ملی > اپن‌لایبرری > گوگل
        self.assertEqual(m["authors"], ["کبری صابر"])
        self.assertEqual(m["publisher"], "نشر نمونه")
        self.assertEqual(m["cover_url"], "https://covers.example/1.jpg")   # جلد: اپن‌لایبرری > گوگل
        self.assertEqual(m["provenance"]["cover_url"], "openlibrary")
        self.assertEqual(m["provenance"]["publisher"], "nlai")

    def test_confidence_formula(self):
        # دو منبع هم‌عنوان (۴۰+۳۰) + ناشر/سال (۲۰) + جلد (۱۰) = ۱۰۰
        self.assertEqual(isbn.merge_records({"nlai": NLAI_REC, "openlibrary": OL_REC})["confidence"], 100)
        # دو منبع ناهم‌عنوان: ۳۰ بونوس نمی‌گیره
        other = {**OL_REC, "title": "یک کتاب کاملاً دیگر"}
        self.assertEqual(isbn.merge_records({"nlai": NLAI_REC, "openlibrary": other})["confidence"], 40 + 20 + 10)
        # یه منبع با ناشر/سال و بدون جلد
        self.assertEqual(isbn.merge_records({"nlai": NLAI_REC})["confidence"], 60)
        self.assertEqual(isbn.merge_records({"google": GOOGLE_REC})["confidence"], 40 + 20 + 10)
        self.assertIsNone(isbn.merge_records({"nlai": None, "google": None}))

    def test_title_key_ignores_space_zwnj_and_arabic_letters(self):
        self.assertEqual(isbn.title_key("مدارس دوست‌داشتنی"), isbn.title_key("مدارس دوست داشتنی"))
        self.assertEqual(isbn.title_key("كلیدر"), isbn.title_key("کلیدر"))

    def test_marc_year_calendar_translator_and_isbn10_record(self):
        from books.tests import marc_record
        rec = marc_record([
            ("010", [("a", "0-306-40615-2")]), ("101", [("a", "per")]),
            ("200", [("a", "کتاب"), ("e", "زیرعنوان"), ("h", "۲")]), ("205", [("a", "چاپ سوم")]),
            ("210", [("c", "ناشر الف"), ("d", "۱۳۹۲")]), ("215", [("a", "۲۴۰ ص.")]),
            ("700", [("a", "هدایت"), ("b", "صادق")]), ("702", [("a", "زبان"), ("b", "مترجم"), ("4", "730")]),
            ("606", [("a", "داستان")]), ("330", [("a", "خلاصه")]),
        ])
        out = isbn._from_marc(isbn.parse_marc(rec)[0], "9780306406157")        # شابک ۱۰ رکورد با ۱۳ پرسیده‌شده یکی حساب می‌شه
        self.assertEqual((out["authors"], out["translators"]), (["صادق هدایت"], ["مترجم زبان"]))
        self.assertEqual((out["year"], out["year_calendar"], out["pages"], out["language"]), (1392, "jalali", 240, "per"))
        self.assertEqual((out["publisher"], out["edition_no"], out["volume"], out["subtitle"]), ("ناشر الف", "چاپ سوم", "۲", "زیرعنوان"))
        self.assertEqual((out["subjects"], out["description"]), (["داستان"], "خلاصه"))
        self.assertEqual(isbn._year_info("c2001"), (2001, "gregorian"))


class CatalogTests(Base):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def patch(self, nlai=None, ol=None, google=None):
        stack = [mock.patch("books.isbn._nlai", return_value=nlai), mock.patch("books.isbn._open_library", return_value=ol),
                 mock.patch("books.isbn._google", return_value=google)]
        mocks = [p.start() for p in stack]
        for p in stack:
            self.addCleanup(p.stop)
        return mocks

    def test_isbn10_and_isbn13_resolve_to_one_edition_and_second_lookup_is_free(self):
        nlai, ol, google = self.patch(nlai=NLAI_REC, ol=OL_REC)
        e1 = catalog.resolve("0-306-40615-2")
        calls = nlai.call_count + ol.call_count + google.call_count
        e2 = catalog.resolve("978-0-306-40615-7")
        e3 = catalog.resolve("۹۷۸۰۳۰۶۴۰۶۱۵۷")
        self.assertEqual((e1.pk, e2.pk, e3.pk), (e1.pk,) * 3)
        self.assertEqual(Edition.objects.count(), 1)
        self.assertEqual(nlai.call_count + ol.call_count + google.call_count, calls)             # صفر تماس شبکه
        self.assertEqual((e1.isbn13, e1.source, e1.confidence, e1.year_calendar), ("9780306406157", "nlai+openlibrary", 100, "jalali"))

    def test_negative_lookup_is_cached_and_makes_no_edition(self):
        nlai, ol, google = self.patch()
        self.assertIsNone(catalog.resolve("9780306406157"))
        self.assertIsNone(catalog.resolve("9780306406157"))
        self.assertEqual(nlai.call_count, 1)
        self.assertFalse(Edition.objects.exists())

    def test_invalid_isbn_never_touches_network_or_db(self):
        nlai, *_ = self.patch(nlai=NLAI_REC)
        self.assertIsNone(catalog.resolve("9789646194485"))
        nlai.assert_not_called()

    def test_user_data_never_overwrites_source_backed_edition(self):
        self.patch(nlai=NLAI_REC)
        sourced = catalog.resolve("9786007547717")
        out = catalog.record_user_entry(self.taker, "9786007547717", "عنوان کاملاً غلط", "نویسنده‌ی جعلی")
        sourced.refresh_from_db()
        self.assertEqual((out.pk, sourced.title, sourced.authors, sourced.source), (sourced.pk, "مدارس دوست‌داشتنی", ["کبری صابر"], "nlai"))
        # ثبت کتاب با شابک منبع‌دار هم عنوان Edition رو عوض نمی‌کنه
        Book.objects.create(owner=self.taker, title="عنوان جعلی", author="کسی", isbn="9786007547717", city=self.tehran)
        sourced.refresh_from_db()
        self.assertEqual(sourced.title, "مدارس دوست‌داشتنی")
        self.assertEqual(Book.objects.get(isbn="9786007547717").edition, sourced)

    def test_user_entry_confidence_20_then_two_independent_matches_raise_it(self):
        e = catalog.record_user_entry(self.giver, "9780306406157", "بوف کور", "هدایت")
        self.assertEqual((e.source, e.confidence), ("user", 20))
        again = catalog.record_user_entry(self.giver, "9780306406157", "بوف کور", "هدایت")     # همان کاربر دوباره شمرده نمی‌شه
        self.assertEqual(again.confidence, 20)
        e2 = catalog.record_user_entry(self.taker, "9780306406157", "بوف  کور", "صادق هدایت")  # کاربر مستقل، عنوان هم‌خوان
        self.assertEqual((e2.pk, e2.confidence), (e.pk, 35))
        third = User.objects.create_user("third", password="x12345678")
        self.assertEqual(catalog.record_user_entry(third, "9780306406157", "بوف کور", "هدایت").confidence, 50)
        self.assertEqual(Edition.objects.count(), 1)

    def test_conflicting_user_title_does_not_change_confidence_or_title(self):
        e = catalog.record_user_entry(self.giver, "9780306406157", "بوف کور", "هدایت")
        out = catalog.record_user_entry(self.taker, "9780306406157", "کتاب دیگری", "کس دیگر")
        e.refresh_from_db()
        self.assertEqual((e.title, e.confidence, out.pk), ("بوف کور", 20, e.pk))
        self.assertEqual(e.provenance["conflicts"][0]["title"], "کتاب دیگری")

    def test_source_data_replaces_user_edition_once_found(self):
        user_ed = catalog.record_user_entry(self.giver, "9786007547717", "نام اشتباه", "الف")
        self.patch(nlai=NLAI_REC)
        resolved = catalog.resolve("9786007547717")
        self.assertEqual((resolved.pk, resolved.title, resolved.source), (user_ed.pk, "مدارس دوست‌داشتنی", "nlai"))
        self.assertEqual(resolved.provenance["users"], [self.giver.pk])

    def test_user_edition_not_requeried_within_a_week(self):
        nlai, *_ = self.patch()
        catalog.record_user_entry(self.giver, "9780306406157", "بوف کور", "هدایت")
        catalog.resolve("9780306406157")
        catalog.resolve("9780306406157")
        self.assertEqual(nlai.call_count, 1)

    def test_edition_isbn_unique_and_book_protects_edition(self):
        e = catalog.record_user_entry(self.giver, "9780306406157", "ک", "ن")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Edition.objects.create(isbn13=e.isbn13, title="دوباره")
        Edition.objects.create(isbn13=None, title="بدون شابک 1")                        # nullable و چندتا مجاز
        Edition.objects.create(isbn13=None, title="بدون شابک 2")
        Book.objects.create(owner=self.giver, title="ک", author="ن", isbn="9780306406157", city=self.tehran)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            e.delete()


class BackfillCommandTests(Base):
    def run_cmd(self, *args):
        out = StringIO()
        call_command("backfill_editions", *args, stdout=out)
        return out.getvalue()

    def test_idempotent_normalizes_legacy_and_skips_invalid(self):
        Book.objects.bulk_create([
            Book(owner=self.giver, title="الف", author="ن", isbn="0306406152", city=self.tehran),          # ISBN-10 قدیمی
            Book(owner=self.giver, title="ب", author="ن", isbn="9780306406157", city=self.tehran),         # همان کتاب، ISBN-13
            Book(owner=self.giver, title="ج", author="ن", isbn="9789646194485", city=self.tehran),         # نامعتبر
            Book(owner=self.giver, title="د", author="ن", isbn="", city=self.tehran),
        ])
        self.assertIn("وصل‌شده: 2", self.run_cmd())
        self.assertEqual(Edition.objects.count(), 1)
        a, b = Book.all_objects.get(title="الف"), Book.all_objects.get(title="ب")
        self.assertEqual((a.isbn, a.edition_id, b.edition_id), ("9780306406157", b.edition_id, Edition.objects.get().pk))
        self.assertEqual(Book.all_objects.get(title="ج").isbn, "9789646194485")                          # دست‌نخورده
        self.assertEqual(Book.all_objects.get(title="ج").edition_id, None)
        again = self.run_cmd()
        self.assertIn("وصل‌شده: 0", again)
        self.assertEqual(Edition.objects.count(), 1)

    def test_dry_run_changes_nothing(self):
        Book.objects.bulk_create([Book(owner=self.giver, title="الف", author="ن", isbn="0306406152", city=self.tehran)])
        self.assertIn("وصل‌شده: 1", self.run_cmd("--dry-run"))
        self.assertEqual((Edition.objects.count(), Book.all_objects.get().isbn, Book.all_objects.get().edition_id), (0, "0306406152", None))

    def test_fetch_enriches_user_editions_from_sources(self):
        Book.objects.bulk_create([Book(owner=self.giver, title="مدارس", author="ن", isbn="9786007547717", city=self.tehran)])
        self.run_cmd()
        cache.clear()
        with mock.patch("books.isbn._nlai", return_value=NLAI_REC), mock.patch("books.isbn._open_library", return_value=None), \
                mock.patch("books.isbn._google", return_value=None):
            self.assertIn("غنی‌شده از منبع: 1", self.run_cmd("--fetch", "--sleep", "0"))
        e = Edition.objects.get()
        self.assertEqual((e.source, e.publisher), ("nlai", "نشر نمونه"))
        self.assertEqual(Book.all_objects.get().title, "مدارس")                                          # فیلدهای قدیمی دست‌نخورده


class IsbnApiTests(Base):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client.login(username="taker", password="x12345678")

    def test_api_returns_edition_demand_duplicates_and_availability(self):
        from exchanges import services
        with mock.patch("books.isbn._nlai", return_value=NLAI_REC), mock.patch("books.isbn._open_library", return_value=None), \
                mock.patch("books.isbn._google", return_value=None):
            mine = Book.objects.create(owner=self.taker, title="مدارس", author="ن", isbn="9786007547717", city=self.tehran)
            other = Book.objects.create(owner=self.giver, title="مدارس دوست‌داشتنی", author="کبری صابر", isbn="9786007547717", city=self.isfahan)
            third = User.objects.create_user("t3", password="x12345678", points=1)
            services.request_book(other.pk, third)
            d = self.client.get(reverse("books:isbn"), {"isbn": "۹۷۸-۶۰۰-۷۵۴۷-۷۱-۷"}).json()
        self.assertEqual((d["title"], d["publisher"], d["year"], d["year_calendar"], d["pages"]), ("مدارس دوست‌داشتنی", "نشر نمونه", 1392, "jalali", 120))
        self.assertEqual((d["mine"], d["available_elsewhere"], d["demand"]), (1, 1, 1))
        self.assertEqual(mine.owner, self.taker)

    def test_api_rejects_checksum_error_with_400(self):
        r = self.client.get(reverse("books:isbn"), {"isbn": "9789646194485"})
        self.assertEqual((r.status_code, r.json()["error"]), (400, "invalid_isbn"))


class DemandTests(Base):
    def test_demand_counts_distinct_wishers_and_requesters_without_self(self):
        from django.test import override_settings
        from books.models import Wishlist
        from books.services import demand_for
        from exchanges import services
        with override_settings(WISHLIST_ENABLED=True):
            Wishlist.objects.create(user=self.taker, text="بوف کور")
            b = self.book(title="بوف کور", isbn="9780306406157")
            ex = services.request_book(b.pk, self.taker)                       # همان taker: یکی شمرده می‌شه
            services.cancel(ex.pk, self.taker)
            self.assertEqual(demand_for("9780306406157", "بوف کور", "هدایت"), 1)
            self.assertEqual(demand_for("9780306406157", "بوف کور", "هدایت", exclude_user=self.taker), 0)


class QualityAndUxTests(Base):
    def test_quality_score_weights_and_tips(self):
        from books.quality import WEIGHTS, listing_quality
        bare = Book.objects.create(owner=self.giver, title="ک", author="ن", city=self.tehran)
        q = listing_quality(bare)
        self.assertEqual(q["score"], WEIGHTS["base"])
        self.assertEqual((q["label"], len(q["tips"])), ("قابل بهبود", 5))
        edition = catalog.record_user_entry(self.giver, "9780306406157", "ک", "ن")
        rich = Book.objects.create(owner=self.giver, title="ک", author="ن", city=self.tehran, category=self.cat, description="توضیح کافی درباره‌ی وضعیت کتاب",
                                   isbn="9780306406157", edition=edition)
        q2 = listing_quality(rich)
        self.assertEqual(q2["score"], WEIGHTS["base"] + WEIGHTS["description"] + WEIGHTS["category"] + WEIGHTS["edition_user"])
        edition.source, edition.confidence = "nlai", 60
        edition.save()
        rich.refresh_from_db()
        self.assertEqual(listing_quality(rich)["score"], q2["score"] - WEIGHTS["edition_user"] + WEIGHTS["edition_backed"])
        self.assertEqual(sum(WEIGHTS[k] for k in ("base", "cover", "description", "category", "edition_backed", "photos")), 100)

    def test_my_books_detail_and_form_expose_quality_demand_and_scan_ui(self):
        book = self.book(title="کتاب من")
        self.client.login(username="giver", password="x12345678")
        self.assertContains(self.client.get(reverse("books:mine")), "کیفیت آگهی")
        detail = self.client.get(book.get_absolute_url())
        self.assertContains(detail, "کیفیت آگهی:")
        form = self.client.get(reverse("books:create"))
        for needle in ('data-scan', 'data-preview', 'id="hv-quality"', "پیش‌نمایش", "js/scan.js", "vendor/zxing/zxing-library.min.js"):
            self.assertContains(form, needle)
        bulk = self.client.get(reverse("books:bulk"))
        self.assertContains(bulk, "data-scan-continuous")
        self.assertEqual(bulk.content.decode().count("data-isbn-scope"), 12)

    def test_demand_line_and_bibliographic_block_on_detail(self):
        from exchanges import services
        edition = catalog.record_user_entry(self.giver, "9786007547717", "مدارس", "ک")
        edition.source, edition.publisher, edition.year, edition.year_calendar = "nlai", "نشر نمونه", 1392, "jalali"
        edition.translators, edition.pages = ["مترجم"], 120
        edition.save()
        book = self.book(title="مدارس", isbn="9786007547717")
        services.request_book(book.pk, self.taker)
        self.client.login(username="giver", password="x12345678")
        page = self.client.get(book.get_absolute_url()).content.decode()
        self.assertTrue("demand-line" in page and "۱ نفر دنبال" in page)       # صاحب کتاب تقاضا رو می‌بینه (خودش شمرده نمی‌شه)
        third = User.objects.create_user("t3", password="x12345678", points=1)
        services.request_book(book.pk, third)
        self.client.login(username="taker", password="x12345678")
        page = self.client.get(book.get_absolute_url()).content.decode()
        self.assertTrue("۲ نفر دنبال" in page)        # taker و third
        for needle in ("نشر نمونه", "مترجم", "۱۳۹۲", "(شمسی)", "9786007547717"):
            self.assertTrue(needle in page, needle)


class CoverageCommandAndAdminTests(Base):
    def test_isbn_coverage_command_reports_percentage(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("# نمونه\n978-600-7547-71-7  # مدارس\n9780140328721\n9789646194485\n")
            path = f.name
        out = StringIO()
        rec = {"isbn": "x", "title": "ت", "authors": ["ن"], "publisher": "ن", "sources": ["nlai"], "confidence": 60, "author": "ن"}
        with mock.patch("books.isbn.lookup_full", side_effect=[rec, None]):
            call_command("isbn_coverage", path, "--sleep", "0", stdout=out)
        text = out.getvalue()
        self.assertTrue("کامل (عنوان+نویسنده+ناشر): 1/2 = 50٪" in text and "شابک نامعتبر" in text, text)

    def test_edition_admin_verify_action(self):
        e = catalog.record_user_entry(self.giver, "9780306406157", "ک", "ن")
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        self.assertEqual(self.client.get("/admin/books/edition/").status_code, 200)
        self.client.post("/admin/books/edition/", {"action": "mark_verified", "_selected_action": [e.pk]})
        e.refresh_from_db()
        self.assertEqual((e.verified, e.confidence), (True, 90))
