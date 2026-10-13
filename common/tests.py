from datetime import timedelta

from common.models import AuditLog
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from books.models import Book, Category, Wishlist
from common.models import City, Province


def make_city(name, province=None):
    """شهر آزمایشی با استان؛ بدون آرگومان دوم، استان هم‌نام شهر."""
    prov, _ = Province.objects.get_or_create(name=province or name)
    return City.objects.get_or_create(province=prov, name=name)[0]
from exchanges import services
from exchanges.models import Exchange
from notifications.models import Notification
from trust.models import Report, Vote
from trust.services import apply_decision, reputation


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.isfahan = make_city("اصفهان")
        cls.tehran = make_city("تهران")
        cls.cat = Category.objects.create(name="رمان")
        cls.giver = User.objects.create_user("giver", password="x12345678", city=cls.isfahan)
        cls.taker = User.objects.create_user("taker", password="x12345678", city=cls.tehran, points=1)

    def book(self, owner=None, **kw):
        return Book.objects.create(
            owner=owner or self.giver, title=kw.pop("title", "بوف کور"), author="هدایت",
            city=self.isfahan, category=self.cat, **kw)

    def complete(self, book=None, taker=None):
        book = book or self.book()
        taker = taker or self.taker
        taker.refresh_from_db()
        ex = services.request_book(book.pk, taker)
        services.accept(ex.pk, ex.owner)
        services.confirm(ex.pk, ex.owner)
        services.confirm(ex.pk, taker)
        ex.refresh_from_db()
        return ex


class ExchangeFlowTests(Base):
    def test_full_flow_moves_points_book_and_journey(self):
        ex = self.complete()
        self.giver.refresh_from_db(); self.taker.refresh_from_db()
        self.assertEqual(ex.status, Exchange.Status.COMPLETED)
        self.assertEqual((self.giver.points, self.taker.points), (1, 0))
        book = ex.book; book.refresh_from_db()
        self.assertEqual(book.owner, self.taker)
        self.assertEqual(book.status, Book.Status.EXCHANGED)
        self.assertEqual(book.city, self.tehran)
        step = book.journey.get()
        self.assertEqual((step.from_city, step.to_city), (self.isfahan, self.tehran))
        self.assertTrue(self.giver.user_badges.filter(badge__code="book-lover").exists())

    def test_newcomer_cannot_request_without_points(self):
        newbie = User.objects.create_user("newbie", password="x12345678")
        with self.assertRaises(services.ExchangeError):
            services.request_book(self.book().pk, newbie)

    def test_points_held_and_refunded_on_cancel(self):
        ex = services.request_book(self.book().pk, self.taker)
        self.taker.refresh_from_db(); self.assertEqual(self.taker.points, 0)
        services.cancel(ex.pk, self.taker)
        self.taker.refresh_from_db(); self.assertEqual(self.taker.points, 1)

    def test_cannot_double_spend_one_point(self):
        services.request_book(self.book().pk, self.taker)
        with self.assertRaises(services.ExchangeError):
            services.request_book(self.book(title="دیگری").pk, self.taker)

    def test_accept_rejects_others_and_refunds(self):
        other = User.objects.create_user("other", password="x12345678", points=1)
        book = self.book()
        a = services.request_book(book.pk, self.taker)
        b = services.request_book(book.pk, other)
        services.accept(a.pk, self.giver)
        b.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(b.status, Exchange.Status.REJECTED)
        self.assertEqual(other.points, 1)

    def test_cancel_accepted_frees_book(self):
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        services.cancel(ex.pk, self.giver)
        ex.book.refresh_from_db()
        self.assertEqual(ex.book.status, Book.Status.AVAILABLE)

    def test_restricted_user_cannot_request_but_can_give(self):
        self.taker.status = User.Status.RESTRICTED
        self.taker.restricted_until = timezone.now() + timedelta(days=1)
        self.taker.save()
        with self.assertRaises(services.ExchangeError):
            services.request_book(self.book().pk, self.taker)
        self.taker.restricted_until = timezone.now() - timedelta(days=1)
        self.taker.save()
        self.assertTrue(self.taker.can_request)

    def test_owner_cannot_request_own_book(self):
        self.giver.points = 5; self.giver.save()
        with self.assertRaises(services.ExchangeError):
            services.request_book(self.book().pk, self.giver)

    def test_only_party_sees_exchange(self):
        ex = services.request_book(self.book().pk, self.taker)
        User.objects.create_user("spy", password="x12345678")
        self.client.login(username="spy", password="x12345678")
        self.assertEqual(self.client.get(reverse("exchanges:detail", args=[ex.pk])).status_code, 404)


class TrustTests(Base):
    def vote_url(self, ex):
        return reverse("trust:vote", args=[ex.pk])

    def test_vote_only_after_completion(self):
        ex = services.request_book(self.book().pk, self.taker)
        self.client.login(username="taker", password="x12345678")
        self.client.post(self.vote_url(ex), {"like": "1"})
        self.assertFalse(Vote.objects.exists())

    def test_vote_edit_window(self):
        ex = self.complete()
        self.client.login(username="taker", password="x12345678")
        self.client.post(self.vote_url(ex), {"like": "1"})
        self.client.post(self.vote_url(ex), {"like": "0", "reason": "mismatch"})
        v = Vote.objects.get()
        self.assertFalse(v.like)
        Vote.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.client.post(self.vote_url(ex), {"like": "1"})
        v.refresh_from_db(); self.assertFalse(v.like)  # قفل شده
        self.assertEqual(Vote.objects.count(), 1)

    def test_newcomer_and_percent(self):
        self.assertTrue(reputation(self.giver)["newcomer"])
        ex = self.complete()
        Vote.objects.create(exchange=ex, voter=self.taker, target=self.giver, like=True)
        r = reputation(self.giver)
        self.assertEqual((r["percent"], r["total"], r["low"]), (100, 1, False))

    def test_low_reputation_needs_min_votes(self):
        for i in range(5):
            voter = User.objects.create_user(f"v{i}", password="x12345678", points=1)
            ex = self.complete(self.book(title=f"b{i}"), voter)
            Vote.objects.create(exchange=ex, voter=voter, target=self.giver, like=(i == 0))
        r = reputation(self.giver)
        self.assertEqual(r["percent"], 20)
        self.assertTrue(r["low"])

    def test_dislike_other_needs_comment(self):
        ex = self.complete()
        self.client.login(username="taker", password="x12345678")
        self.client.post(self.vote_url(ex), {"like": "0", "reason": "other"})
        self.assertFalse(Vote.objects.exists())

    def test_mutual_pairs_weigh_less(self):
        for i in range(3):  # سه مبادله‌ی دو نفره: وزن ۰٫۵
            self.taker.refresh_from_db(); self.taker.points = 1; self.taker.save()
            ex = self.complete(self.book(title=f"p{i}"))
            Vote.objects.create(exchange=ex, voter=self.taker, target=self.giver, like=(i < 2))
        # ۲ لایک از ۳، همه با وزن برابر، پس همچنان ۶۷٪
        self.assertEqual(reputation(self.giver)["percent"], 67)

    def test_report_once_per_target(self):
        book = self.book()
        self.client.login(username="taker", password="x12345678")
        url = reverse("trust:report", args=["book", book.pk])
        self.client.post(url, {"reason": "bad_book", "description": "x"})
        self.client.post(url, {"reason": "bad_book", "description": "y"})
        self.assertEqual(Report.objects.count(), 1)

    def test_cannot_report_self(self):
        self.client.login(username="giver", password="x12345678")
        self.client.post(reverse("trust:report", args=["user", self.giver.pk]), {"reason": "other"})
        self.assertFalse(Report.objects.exists())

    def test_decisions(self):
        r = Report.objects.create(reporter=self.taker, target_user=self.giver, reason="no_show", decision="restrict", decision_note="n")
        apply_decision(r, self.taker)
        self.giver.refresh_from_db(); r.refresh_from_db()
        self.assertTrue(self.giver.is_restricted)
        self.assertEqual(r.status, Report.Status.CLOSED)
        self.assertTrue(Notification.objects.filter(user=self.taker).exists())

    def test_ban_blocks_login(self):
        r = Report.objects.create(reporter=self.taker, target_user=self.giver, reason="scam", decision="ban", decision_note="n")
        apply_decision(r, self.taker)
        self.assertFalse(self.client.login(username="giver", password="x12345678"))

    def test_repeated_no_show_auto_restricts(self):
        for i in range(3):
            reporter = User.objects.create_user(f"r{i}", password="x12345678")
            r = Report.objects.create(reporter=reporter, target_user=self.giver, reason="no_show", decision="warn", decision_note="n")
            apply_decision(r, self.taker)
        self.giver.refresh_from_db()
        self.assertEqual(self.giver.warnings, 3)
        self.assertTrue(self.giver.is_restricted)

    def test_reject_warn_reporter(self):
        r = Report.objects.create(reporter=self.taker, target_user=self.giver, reason="other", decision="reject_warn", decision_note="n")
        apply_decision(r, self.giver)
        self.taker.refresh_from_db()
        self.assertEqual(self.taker.warnings, 1)


class BookTests(Base):
    def test_search_filters(self):
        self.book(title="الف"); self.book(title="ب", condition="new")
        r = self.client.get(reverse("books:list"), {"q": "الف"})
        self.assertEqual(len(r.context["page"]), 1)
        r = self.client.get(reverse("books:list"), {"condition": "new", "city": self.isfahan.pk})
        self.assertEqual([b.title for b in r.context["page"]], ["ب"])

    def test_wishlist_is_coming_soon_when_disabled(self):
        from notifications.models import Notification
        self.client.login(username="taker", password="x12345678")
        r = self.client.get("/books/wishlist/")
        self.assertContains(r, "به‌زودی")
        self.assertNotContains(r, 'name="text"')
        before = Wishlist.objects.count()
        self.client.post("/books/wishlist/", {"text": "بوف"})
        self.assertEqual(Wishlist.objects.count(), before)
        Wishlist.objects.create(user=self.taker, text="بوف")
        self.book(title="بوف کور")
        self.assertFalse(Notification.objects.filter(user=self.taker, kind="wishlist").exists())
        from common.onboarding import steps
        self.assertFalse(any("لیست آرزو" in st["title"] for st in steps(self.taker)))

    @override_settings(WISHLIST_ENABLED=True)
    def test_wishlist_notifies(self):
        Wishlist.objects.create(user=self.taker, text="بوف")
        self.client.login(username="giver", password="x12345678")
        self.client.post(reverse("books:create"), {
            "title": "بوف کور", "author": "هدایت", "condition": "used", "city": self.isfahan.pk})
        self.assertEqual(Notification.objects.filter(user=self.taker).count(), 1)

    def test_note_and_relist(self):
        ex = self.complete()
        self.client.login(username="giver", password="x12345678")
        self.client.post(reverse("exchanges:note", args=[ex.pk]), {"text": "بخون!"})
        self.assertEqual(ex.book.notes.count(), 1)
        self.client.login(username="taker", password="x12345678")
        url = reverse("books:relist", args=[ex.book.pk])
        self.assertEqual(self.client.get(url).status_code, 200)       # فرم شهر
        self.client.post(url, {})                                     # بدون شهر: ثبت نمی‌شه
        ex.book.refresh_from_db(); self.assertEqual(ex.book.status, Book.Status.EXCHANGED)
        self.client.post(url, {"province": self.tehran.province_id, "city": self.tehran.pk})
        ex.book.refresh_from_db()
        self.assertEqual((ex.book.status, ex.book.city), (Book.Status.AVAILABLE, self.tehran))

    def test_pages_render(self):
        ex = self.complete()
        self.client.login(username="taker", password="x12345678")
        for url in ["/", "/books/", f"/books/{ex.book.pk}/", "/books/new/", "/books/mine/", "/books/wishlist/",
                    "/exchanges/", f"/exchanges/{ex.pk}/", "/notifications/", "/accounts/u/giver/", "/accounts/settings/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_signup_flow(self):
        r = self.client.post(reverse("accounts:signup"), {
            "username": "newuser", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99", "city": self.tehran.pk, "accept_rules": "on"})
        self.assertEqual(r.status_code, 302)
        u = User.objects.get(username="newuser")
        self.assertEqual(u.points, 1)  # امتیاز خوش‌آمد (آی‌پی لوکال شمرده نمی‌شه)
        self.assertTrue(u.welcome_granted)


class IsbnAndBulkTests(Base):
    def test_normalize(self):
        from books.isbn import normalize
        self.assertEqual(normalize("978-964-6194-48-9"), "9789646194489")
        self.assertEqual(normalize("۹۷۸۹۶۴۶۱۹۴۴۸۹"), "9789646194489")
        self.assertEqual(normalize("0-306-40615-2"), "9780306406157")          # ISBN-10 ← ISBN-13
        self.assertIsNone(normalize("978-964-6194-48-5"))                      # رقم کنترل غلط
        self.assertIsNone(normalize("12345"))

    def test_lookup_parses_and_caches(self):
        from unittest import mock
        from django.core.cache import cache
        from books import isbn
        cache.clear()
        body = {"ISBN:9780140328721": {"title": "Fantastic Mr Fox", "authors": [{"name": "Roald Dahl"}]}}
        with (
            mock.patch("books.isbn._nlai", return_value=None),
            mock.patch("books.isbn._google", return_value=None),
            mock.patch("books.isbn._fetch", return_value=body) as m,
        ):
            r = isbn.lookup("978-0-14-032872-1")
            isbn.lookup("9780140328721")
        self.assertEqual((r["isbn"], r["title"], r["author"]), ("9780140328721", "Fantastic Mr Fox", "Roald Dahl"))
        self.assertEqual(m.call_count, 1)                                  # دومی از کش اومد

    def test_book_with_isbn_gets_user_edition_and_resolve_uses_it(self):
        from unittest import mock
        from books import catalog
        Book.objects.create(owner=self.giver, title="بوف کور", author="صادق هدایت", isbn="9789643051099", city=self.tehran)
        ed = Book.objects.get(isbn="9789643051099").edition
        self.assertEqual((ed.source, ed.confidence, ed.authors), ("user", 20, ["صادق هدایت"]))
        with mock.patch("books.isbn.lookup_full") as m:
            self.assertEqual(catalog.resolve("۹۷۸۹۶۴۳۰۵۱۰۹۹", fetch=False), ed)
        m.assert_not_called()

    def test_lookup_falls_back_to_google(self):
        import urllib.error
        from unittest import mock
        from django.core.cache import cache
        from books import isbn
        cache.clear()
        g = {"isbn": "9789643051099", "title": "کلیدر", "author": "دولت‌آبادی", "authors": ["دولت‌آبادی"]}
        with (
            mock.patch("books.isbn._nlai", return_value=None),
            mock.patch("books.isbn._open_library", return_value=None),
            mock.patch("books.isbn._google", return_value=g),
        ):
            r = isbn.lookup("9789643051099")
        self.assertEqual(r["title"], "کلیدر")
        cache.clear()
        with (
            mock.patch("books.isbn._nlai", return_value=None),
            mock.patch("books.isbn._open_library", side_effect=urllib.error.URLError("x")),
            mock.patch("books.isbn._google", return_value=None),
        ):
            self.assertIsNone(isbn.lookup("9780306406157"))
            self.assertIsNone(cache.get("isbn2:9780306406157"))  # با خطای شبکه نتیجه‌ی منفی کش نمی‌شه

    def test_lookup_network_error_is_none(self):
        import urllib.error
        from unittest import mock
        from django.core.cache import cache
        from books import isbn
        cache.clear()
        err = urllib.error.URLError("x")
        with (
            mock.patch("books.isbn._nlai", side_effect=err),
            mock.patch("books.isbn._open_library", side_effect=err),
            mock.patch("books.isbn._google", side_effect=err),
        ):
            self.assertIsNone(isbn.lookup("9780140328721"))

    def test_isbn_view_requires_login_400_404_and_data(self):
        from unittest import mock
        url = reverse("books:isbn")
        self.assertEqual(self.client.get(url, {"isbn": "9780140328721"}).status_code, 302)
        self.client.login(username="giver", password="x12345678")
        r = self.client.get(url, {"isbn": "9780140328722"})                          # رقم کنترل غلط
        self.assertEqual((r.status_code, r.json()["error"]), (400, "invalid_isbn"))
        with mock.patch("books.isbn.lookup_full", return_value=None):
            self.assertEqual(self.client.get(url, {"isbn": "9780140328721"}).status_code, 404)
        rich = {"isbn": "9780140328721", "title": "T", "author": "A", "authors": ["A"], "publisher": "ناشر", "year": 1390, "year_calendar": "jalali",
                "sources": ["nlai"], "provenance": {}, "confidence": 60}
        with mock.patch("books.isbn.lookup_full", return_value=rich):
            data = self.client.get(url, {"isbn": "0-14-032872-6"}).json()   # ISBN-10 هم‌ارز
        self.assertEqual((data["title"], data["publisher"], data["isbn"], data["confidence"]), ("T", "ناشر", "9780140328721", 60))

    def _bulk_data(self, rows):
        data = {"city": self.isfahan.pk, "condition": "used", "form-TOTAL_FORMS": 12, "form-INITIAL_FORMS": 0,
                "form-MIN_NUM_FORMS": 0, "form-MAX_NUM_FORMS": 12}
        for i in range(12):
            row = rows[i] if i < len(rows) else {}
            for k in ("isbn", "title", "author", "category"):
                data[f"form-{i}-{k}"] = row.get(k, "")
        return data

    def test_bulk_creates_filled_rows_only(self):
        Wishlist.objects.create(user=self.taker, text="هدایت")
        self.client.login(username="giver", password="x12345678")
        r = self.client.post(reverse("books:bulk"), self._bulk_data([
            {"title": "الف", "author": "ن۱", "isbn": "978-0-14-032872-1"},
            {"title": "ب", "author": "ن۲", "category": self.cat.pk},
        ]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Book.objects.filter(owner=self.giver).count(), 2)
        self.assertEqual(Book.objects.get(title="الف").isbn, "9780140328721")
        self.assertEqual(Book.objects.get(title="ب").city, self.isfahan)

    def test_bulk_half_filled_row_rejected_atomically(self):
        self.client.login(username="giver", password="x12345678")
        r = self.client.post(reverse("books:bulk"), self._bulk_data([
            {"title": "الف", "author": "ن"}, {"title": "بدون نویسنده"}]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Book.objects.exists())

    def test_bulk_empty_and_bad_isbn(self):
        self.client.login(username="giver", password="x12345678")
        self.assertEqual(self.client.post(reverse("books:bulk"), self._bulk_data([])).status_code, 200)
        r = self.client.post(reverse("books:bulk"), self._bulk_data([{"title": "x", "author": "y", "isbn": "12"}]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Book.objects.exists())


class CityPageTests(Base):
    def test_city_stats(self):
        self.complete()  # اصفهان ← تهران
        self.book(title="دیگر")
        r = self.client.get(reverse("city", args=[self.isfahan.pk]))
        self.assertEqual(r.context["stats"], {"available": 1, "exchanged": 1, "users": 1})
        r = self.client.get(reverse("city", args=[self.tehran.pk]))
        self.assertEqual(r.context["stats"]["exchanged"], 1)  # مقصد هم حساب می‌شه
        self.assertEqual(r.context["stats"]["available"], 0)  # کتاب گیرنده هنوز «مبادله‌شده»ست

    def test_city_list_grouped_by_province_only_with_books(self):
        self.book()
        r = self.client.get(reverse("cities"))
        groups = r.context["groups"]
        self.assertEqual([(g["province"].name, [c.name for c in g["cities"]]) for g in groups], [("اصفهان", ["اصفهان"])])
        self.assertEqual(self.client.get(reverse("city", args=[9999])).status_code, 404)
        self.assertEqual(self.client.get(reverse("province", args=[self.isfahan.province_id])).context["stats"]["available"], 1)
        self.assertEqual(self.client.get(reverse("province", args=[9999])).status_code, 404)

class ReviewShelfChallengeTests(Base):
    def test_only_receiver_can_review_and_edit(self):
        ex = self.complete()
        url = reverse("books:review", args=[ex.book.pk])
        self.client.login(username="giver", password="x12345678")  # دهنده نمی‌تونه
        self.client.post(url, {"stars": 5})
        self.assertEqual(ex.book.reviews.count(), 0)
        self.client.login(username="taker", password="x12345678")
        self.client.post(url, {"stars": 4, "text": "عالی"})
        self.client.post(url, {"stars": 2, "text": "نه"})  # ویرایش، نه رکورد دوم
        r = ex.book.reviews.get()
        self.assertEqual((r.stars, r.text), (2, "نه"))
        self.client.post(url, {"stars": 9})
        self.assertEqual(ex.book.reviews.get().stars, 2)
        page = self.client.get(reverse("books:detail", args=[ex.book.pk]))
        self.assertEqual(page.context["rating"], {"avg": 2.0, "n": 1})

    def test_shelf_shows_owned_hides_reserved(self):
        self.book(title="موجود")
        self.book(title="رزرو", status=Book.Status.RESERVED)
        r = self.client.get(reverse("accounts:profile", args=["giver"]))
        self.assertEqual([b.title for b in r.context["books"]], ["موجود"])
        self.complete(self.book(title="رفت"))
        r = self.client.get(reverse("accounts:profile", args=["taker"]))
        self.assertEqual([b.title for b in r.context["books"]], ["رفت"])  # گرفته و هنوز نذاشته

    def _challenge(self, **kw):
        from challenges.models import Challenge
        now = timezone.now()
        d = dict(title="سه کتاب", kind="give", target=2, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30))
        d.update(kw)
        return Challenge.objects.create(**d)

    def test_challenge_progress_and_badge(self):
        c = self._challenge()
        self.complete(self.book(title="1"))
        self.assertEqual(c.progress(self.giver), 1)
        self.assertFalse(self.giver.user_badges.filter(badge__code=c.badge_code).exists())
        self.taker.refresh_from_db(); self.taker.points = 1; self.taker.save()
        self.complete(self.book(title="2"))
        self.assertTrue(self.giver.user_badges.filter(badge__code=c.badge_code).exists())
        self.assertEqual(c.progress(self.taker), 0)  # نوع «دادن»

    def test_challenge_kinds_and_window(self):
        recv = self._challenge(kind="receive", target=1)
        old = self._challenge(title="قدیمی", starts_at=timezone.now() - timedelta(days=60), ends_at=timezone.now() - timedelta(days=30))
        self.complete()
        self.assertEqual(recv.progress(self.taker), 1)
        self.assertEqual(old.progress(self.giver), 0)
        self.assertFalse(self.giver.user_badges.filter(badge__code=old.badge_code).exists())

    def test_challenge_page(self):
        self._challenge()
        self.assertEqual(self.client.get(reverse("challenges:list")).status_code, 200)
        self.client.login(username="giver", password="x12345678")
        r = self.client.get(reverse("challenges:list"))
        self.assertEqual(r.context["items"][0]["percent"], 0)


class SimilarTests(Base):
    def test_same_work_people_books_and_category_fallback(self):
        from books.services import same_work, similar_books
        a = self.book(title="بوف کور")
        copy = self.book(title="بوف کور", owner=self.taker)       # نسخه‌ی دیگه
        other = self.book(title="سه قطره خون", owner=self.taker)    # مال کسی که نسخه‌ی دیگه رو داره
        stranger = User.objects.create_user("s", password="x12345678")
        unrelated = Book.objects.create(owner=stranger, title="درسی", author="ز", city=self.tehran)
        same_cat = Book.objects.create(owner=stranger, title="رمان دیگر", author="ز", city=self.tehran, category=self.cat)
        self.assertIn(copy, same_work(a))
        got = similar_books(a)
        self.assertEqual(got[0], other)        # اول هم‌سلیقه
        self.assertIn(same_cat, got)           # بعد هم‌دسته
        self.assertNotIn(unrelated, got)
        self.assertNotIn(copy, got)            # خود کتاب نمی‌آد
        self.assertNotIn(a, got)

    def test_exchange_participants_count_and_isbn_match(self):
        from books.services import similar_books
        a = self.book(isbn="9780140328721")
        self.complete(a)                  # taker گرفته (a الان مال taker)
        mine = Book.objects.create(owner=self.giver, title="آخرین", author="ن", city=self.isfahan)
        c = Book.objects.create(owner=self.taker, title="x", author="y", city=self.tehran, isbn="9780140328721")
        got = similar_books(c)
        self.assertIn(mine, got)               # دهنده‌ی نسخه‌ی دیگه
        self.assertTrue(self.client.get(reverse("books:detail", args=[c.pk])).status_code == 200)


class MeetingAndCardTests(Base):
    def setUp(self):
        from common.models import MeetingPoint
        self.p1 = MeetingPoint.objects.create(city=self.isfahan, name="میدان امام", kind="metro")
        self.p2 = MeetingPoint.objects.create(city=self.tehran, name="کافه کتاب", kind="cafe")
        self.far = MeetingPoint.objects.create(city=make_city("یزد"), name="دور", kind="cafe")
        self.off = MeetingPoint.objects.create(city=self.isfahan, name="غیرفعال", kind="cafe", is_active=False)
        self.ex = services.request_book(self.book().pk, self.taker)

    def test_only_after_accept_and_only_allowed_points(self):
        with self.assertRaises(services.ExchangeError):
            services.propose_meeting(self.ex.pk, self.taker, self.p1.pk)  # هنوز تأیید نشده
        services.accept(self.ex.pk, self.giver)
        self.assertEqual({p.pk for p in services.meeting_options(self.ex)}, {self.p1.pk, self.p2.pk})
        for bad in (self.far.pk, self.off.pk, 0):
            with self.assertRaises(services.ExchangeError):
                services.propose_meeting(self.ex.pk, self.taker, bad)

    def test_propose_agree_flow(self):
        services.accept(self.ex.pk, self.giver)
        services.propose_meeting(self.ex.pk, self.taker, self.p1.pk)
        with self.assertRaises(services.ExchangeError):
            services.agree_meeting(self.ex.pk, self.taker)  # پیشنهاددهنده نمی‌تونه
        ex = services.agree_meeting(self.ex.pk, self.giver)
        self.assertTrue(ex.meeting_agreed)
        self.assertEqual(ex.messages.count(), 2)  # پیشنهاد + تأیید تو چت
        ex = services.propose_meeting(self.ex.pk, self.giver, self.p2.pk)  # پیشنهاد جدید تأیید رو ریست می‌کنه
        self.assertFalse(ex.meeting_agreed)
        self.assertTrue(Notification.objects.filter(user=self.taker, text__contains="کافه کتاب").exists())

    def test_third_party_blocked_and_page(self):
        services.accept(self.ex.pk, self.giver)
        stranger = User.objects.create_user("st", password="x12345678")
        with self.assertRaises(services.ExchangeError):
            services.propose_meeting(self.ex.pk, stranger, self.p1.pk)
        self.client.login(username="taker", password="x12345678")
        r = self.client.post(reverse("exchanges:meeting", args=[self.ex.pk]), {"point": self.p1.pk})
        self.assertEqual(r.status_code, 302)
        self.assertContains(self.client.get(reverse("exchanges:detail", args=[self.ex.pk])), "میدان امام")

    def test_share_card_png(self):
        b = self.book(title="کارت")
        r = self.client.get(reverse("books:card", args=[b.pk]), {"download": 1})
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertTrue(b"".join(r.streaming_content).startswith(b"\x89PNG"))
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("books:card", args=[99999])).status_code, 404)

    def test_wrap_truncates_long_titles(self):
        from books.card import _font, wrap
        lines = wrap("کلمه " * 80, _font(True, 72), 900, 2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"))


class PersianTextTests(Base):
    def test_normalize(self):
        from common.text import normalize, work_key
        self.assertEqual(normalize("كتاب  ‌خوانيِ ۱۲۳"), "کتاب خوانی 123")
        self.assertEqual(normalize("بُوفِ‌ کور"), "بوف کور")
        self.assertEqual(work_key("بوف کور", "هدایت"), work_key("بوفِ‌کور", "هدايت"))

    def test_search_ignores_arabic_letters_digits_zwnj(self):
        Book.objects.create(owner=self.giver, title="کتاب‌خانه‌ی ۱۴۰۰", author="علی", city=self.isfahan)
        for q in ("كتابخانه", "کتاب خانه 1400".replace(" 1400", ""), "کتابخانهی ۱۴۰۰", "علي"):
            r = self.client.get(reverse("books:list"), {"q": q})
            self.assertEqual(len(r.context["page"]), 1, q)
        self.assertEqual(len(self.client.get(reverse("books:list"), {"q": "ناموجود"}).context["page"]), 0)

    def test_search_text_updates_on_edit(self):
        b = self.book(title="الف")
        b.title = "كتاب نو"
        b.save()
        b.refresh_from_db()
        self.assertIn("کتاب نو", b.search_text)

    @override_settings(WISHLIST_ENABLED=True)
    def test_same_work_and_wishlist_use_normalization(self):
        from books.services import same_work
        a = Book.objects.create(owner=self.giver, title="بوف کور", author="هدايت", city=self.isfahan)
        b = Book.objects.create(owner=self.taker, title="بوفِ‌کور", author="هدایت", city=self.tehran)
        self.assertIn(b, same_work(a))
        Wishlist.objects.create(user=self.taker, text="هدايت")
        self.client.login(username="giver", password="x12345678")
        self.client.post(reverse("books:create"), {"title": "سه قطره خون", "author": "هدایت", "condition": "used", "city": self.isfahan.pk})
        self.assertTrue(Notification.objects.filter(user=self.taker, text__contains="سه قطره").exists())


class ThrottleTests(Base):
    def test_login_throttled_by_ip(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(20):
            self.client.post(reverse("accounts:login"), {"username": "giver", "password": "wrong"})
        r = self.client.post(reverse("accounts:login"), {"username": "giver", "password": "x12345678"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)  # GET آزاده

    def test_chat_and_isbn_limits_json(self):
        from django.core.cache import cache
        cache.clear()
        ex = services.request_book(self.book().pk, self.taker)
        self.client.login(username="taker", password="x12345678")
        for _ in range(30):
            self.client.post(reverse("exchanges:message", args=[ex.pk]), {"text": "x"})
        r = self.client.post(reverse("exchanges:message", args=[ex.pk]), {"text": "x"}, headers={"x-requested-with": "XMLHttpRequest"})
        self.assertEqual((r.status_code, r.json()["error"]), (429, "rate_limited"))
        # شمارنده‌ها مستقل از هم‌ان
        self.assertEqual(self.client.get(reverse("books:isbn"), {"isbn": "12"}).status_code, 400)

    def test_throttle_disabled_and_proxy_ip(self):
        from django.core.cache import cache
        from django.test import RequestFactory, override_settings
        from common.throttle import client_ip, hit
        cache.clear()
        rf = RequestFactory().get("/", HTTP_X_REAL_IP="5.6.7.8", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(client_ip(rf), "10.0.0.1")  # بدون اعتماد به پروکسی، هدر نادیده‌ست
        with override_settings(TRUST_PROXY_HEADERS=True):
            self.assertEqual(client_ip(rf), "5.6.7.8")
        with override_settings(THROTTLE_ENABLED=False):
            self.assertTrue(all(hit("x", "y", 1, 60) for _ in range(5)))

    def test_signup_honeypot(self):
        from django.core.cache import cache
        cache.clear()
        data = {"username": "bot", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99", "website": "http://spam", "accept_rules": "on"}
        self.client.post(reverse("accounts:signup"), data)
        self.assertFalse(User.objects.filter(username="bot").exists())


class ChatTests(Base):
    def setUp(self):
        self.ex = services.request_book(self.book().pk, self.taker)
        services.accept(self.ex.pk, self.giver)

    def say(self, who, text):
        self.client.login(username=who, password="x12345678")
        return self.client.post(reverse("exchanges:message", args=[self.ex.pk]), {"text": text},
                                headers={"x-requested-with": "XMLHttpRequest"})

    def test_unread_counts_and_mark_read(self):
        from exchanges.chat import total_unread
        self.say("taker", "سلام"); self.say("taker", "هستی؟")
        self.assertEqual(total_unread(self.giver), 2)
        self.assertEqual(total_unread(self.taker), 0)  # پیام خودش خوانده‌نشده نیست
        self.client.login(username="giver", password="x12345678")
        page = self.client.get(reverse("exchanges:list"))
        self.assertEqual(page.context["exchanges"][0].unread, 2)
        self.assertContains(page, "پیام جدید")
        self.client.get(reverse("exchanges:detail", args=[self.ex.pk]))  # باز کردن چت = خوانده شد
        self.assertEqual(total_unread(self.giver), 0)
        self.say("taker", "سوم")
        self.assertEqual(total_unread(self.giver), 1)

    def test_poll_returns_only_new_and_marks_read(self):
        from exchanges.chat import total_unread
        self.say("taker", "یک"); self.say("taker", "دو")
        first = self.ex.messages.first().pk
        self.client.login(username="giver", password="x12345678")
        data = self.client.get(reverse("exchanges:poll", args=[self.ex.pk]), {"after": first}).json()
        self.assertEqual([m["text"] for m in data["messages"]], ["دو"])
        self.assertFalse(data["messages"][0]["mine"])
        self.assertTrue(data["messages"][0]["report_url"])
        self.assertEqual(total_unread(self.giver), 0)

    def test_poll_forbidden_for_strangers_and_bad_after(self):
        User.objects.create_user("st", password="x12345678")
        self.client.login(username="st", password="x12345678")
        self.assertEqual(self.client.get(reverse("exchanges:poll", args=[self.ex.pk])).status_code, 403)
        self.client.login(username="giver", password="x12345678")
        self.assertEqual(self.client.get(reverse("exchanges:poll", args=[self.ex.pk]), {"after": "abc"}).status_code, 200)

    def test_notification_not_duplicated_per_message(self):
        self.say("taker", "۱"); self.say("taker", "۲"); self.say("taker", "۳")
        self.assertEqual(Notification.objects.filter(user=self.giver, text__startswith="پیام تازه").count(), 1)

    def test_ajax_send_returns_json_and_blank_ignored(self):
        self.assertEqual(self.say("taker", "سلام").json(), {"ok": True})
        self.assertEqual(self.say("taker", "   ").json(), {"ok": False})
        self.assertEqual(self.ex.messages.count(), 1)


class JalaliTests(TestCase):
    def test_dates_and_digits(self):
        import datetime
        from common import jalali
        self.assertEqual(jalali.jdate(datetime.date(2026, 3, 21)), "۱۴۰۵/۰۱/۰۱")
        self.assertEqual(jalali.jdate(datetime.date(2026, 10, 12), long=True), "۲۰ مهر ۱۴۰۵")
        self.assertEqual(jalali.fa_digits("a1b2"), "a۱b۲")
        now = timezone.now()
        self.assertEqual(jalali.ago(now - timedelta(hours=3), now), "۳ ساعت پیش")
        self.assertEqual(jalali.ago(now - timedelta(seconds=5), now), "همین الان")
        self.assertRegex(jalali.ago(now - timedelta(days=30), now), r"^۱۴\d\d/")
        self.assertEqual(jalali.jtime(timezone.make_aware(datetime.datetime(2026, 1, 1, 9, 5), datetime.timezone.utc)), "۱۲:۳۵")  # تهران +۳:۳۰

    def test_template_filters_load_globally(self):
        from django.template import Template, Context
        out = Template("{{ n|fa }} {{ d|jdate }}").render(Context({"n": 12, "d": timezone.now()}))
        self.assertIn("۱۲", out)
        self.assertNotRegex(out, "[0-9]")


class DashboardAndSeoTests(Base):
    def test_dashboard_staff_only_and_suspicious(self):
        for i in range(3):  # سه مبادله‌ی بین یه جفت
            self.taker.refresh_from_db(); self.taker.points = 1; self.taker.save()
            self.complete(self.book(title=f"c{i}"))
        r = self.client.get(reverse("panel:index"))
        self.assertEqual(r.status_code, 302)  # لاگین نیست
        self.client.login(username="taker", password="x12345678")
        self.assertEqual(self.client.get(reverse("panel:index")).status_code, 302)  # staff نیست
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        r = self.client.get(reverse("panel:index"))
        self.assertEqual(r.status_code, 200)
        names = {u.username for u, _ in r.context["d"]["suspicious"]}
        self.assertEqual(names, {"giver", "taker"})
        self.assertEqual(r.context["d"]["exchanges"]["completed7"], 3)
        self.assertEqual(len(r.context["d"]["daily"]["completed"]), 14)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_stale_and_reports_counts(self):
        from common.stats import collect
        ex = services.request_book(self.book().pk, self.taker)
        Exchange.objects.filter(pk=ex.pk).update(updated_at=timezone.now() - timedelta(days=10))
        Report.objects.create(reporter=self.taker, target_user=self.giver, reason="other")
        s = collect()
        self.assertEqual(s["exchanges"]["stale_requested"], 1)
        self.assertEqual((s["reports"]["open"], s["reports"]["oldest_days"]), (1, 0))

    def test_daily_report_command(self):
        from io import StringIO
        from django.core import mail
        from django.core.management import call_command
        from django.test import override_settings
        out = StringIO()
        call_command("daily_report", stdout=out)
        self.assertIn("کاربر: 2", out.getvalue())
        with override_settings(ADMIN_EMAILS=["a@b.c"]):
            call_command("daily_report", "--email", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)

    def test_seo_endpoints(self):
        b = self.book(title="سئو")
        self.book(title="رزرو", status=Book.Status.RESERVED)
        sm = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(f"/books/{b.pk}/", sm)
        self.assertIn("/cities/", sm)
        self.assertNotIn("/exchanges/", sm)
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /exchanges/", robots)
        self.assertIn("Sitemap: http", robots)
        sw = self.client.get("/sw.js")
        self.assertEqual(sw["Service-Worker-Allowed"], "/")
        self.assertEqual(self.client.get("/offline/").status_code, 200)

    def test_book_page_meta_and_noindex_headers(self):
        b = self.book(title='عنوان </script> خطرناک')
        r = self.client.get(reverse("books:detail", args=[b.pk]))
        html = r.content.decode()
        self.assertIn('property="og:title"', html)
        self.assertIn('application/ld+json', html)
        ld = html.split('application/ld+json">')[1].split("</script>")[0]
        self.assertNotIn("<", ld)  # نمی‌تونه از تگ script بیرون بزنه
        self.assertIn("/books/%d/card.png" % b.pk, html)
        self.assertNotIn("noindex", r.get("X-Robots-Tag", ""))
        self.assertIn("noindex", self.client.get("/accounts/login/")["X-Robots-Tag"])
        self.assertIn("noindex", self.client.get("/accounts/u/giver/")["X-Robots-Tag"])


class LifecycleTests(Base):
    def age(self, ex, days, **fields):
        t = timezone.now() - timedelta(days=days)
        Exchange.objects.filter(pk=ex.pk).update(created_at=t, **{k: (t if v is True else v) for k, v in fields.items()})

    def run_cycle(self):
        from exchanges.services import process_lifecycle
        return process_lifecycle()

    def test_request_remind_once_then_expire_and_refund(self):
        ex = services.request_book(self.book().pk, self.taker)
        self.assertEqual(self.run_cycle(), {"reminded": 0, "cancelled": 0, "disputed": 0, "relist_reminded": 0})
        self.age(ex, 3)
        self.assertEqual(self.run_cycle()["reminded"], 1)
        self.assertEqual(self.run_cycle()["reminded"], 0)  # دوباره اجرا اعلان تکراری نمی‌سازه
        self.assertEqual(Notification.objects.filter(user=self.giver, text__contains="منتظر جواب").count(), 1)
        self.age(ex, 8)
        self.assertEqual(self.run_cycle()["cancelled"], 1)
        ex.refresh_from_db(); self.taker.refresh_from_db()
        self.assertEqual((ex.status, self.taker.points), (Exchange.Status.CANCELLED, 1))

    def test_accepted_reminders_then_expire_frees_book(self):
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        Exchange.objects.filter(pk=ex.pk).update(accepted_at=timezone.now() - timedelta(days=8))
        self.assertEqual(self.run_cycle()["reminded"], 1)
        self.assertTrue(Notification.objects.filter(user=self.taker, text__contains="هنوز تحویل نشده").exists())
        Exchange.objects.filter(pk=ex.pk).update(accepted_at=timezone.now() - timedelta(days=15))
        self.assertEqual(self.run_cycle()["reminded"], 1)  # یادآوری دوم
        Exchange.objects.filter(pk=ex.pk).update(accepted_at=timezone.now() - timedelta(days=22))
        self.assertEqual(self.run_cycle()["cancelled"], 1)
        ex.refresh_from_db(); ex.book.refresh_from_db(); self.taker.refresh_from_db()
        self.assertEqual((ex.status, ex.book.status, self.taker.points), (Exchange.Status.CANCELLED, Book.Status.AVAILABLE, 1))

    def test_one_sided_confirm_remind_then_auto_dispute(self):
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        services.confirm(ex.pk, self.giver)  # فقط دهنده تأیید کرد
        ex.refresh_from_db(); self.assertIsNotNone(ex.first_confirmed_at)
        Exchange.objects.filter(pk=ex.pk).update(first_confirmed_at=timezone.now() - timedelta(days=4))
        self.assertEqual(self.run_cycle()["reminded"], 1)
        self.assertTrue(Notification.objects.filter(user=self.taker, text__contains="تأیید کرده").exists())
        Exchange.objects.filter(pk=ex.pk).update(first_confirmed_at=timezone.now() - timedelta(days=8))
        self.assertEqual(self.run_cycle()["disputed"], 1)
        ex.refresh_from_db()
        self.assertIsNotNone(ex.disputed_at)
        rep = Report.objects.get()
        self.assertEqual((rep.reporter, rep.target_user), (self.giver, self.taker))  # تأییدکننده شاکیه
        self.assertEqual(self.run_cycle(), {"reminded": 0, "cancelled": 0, "disputed": 0, "relist_reminded": 0})  # از انقضا خارجه
        Exchange.objects.filter(pk=ex.pk).update(accepted_at=timezone.now() - timedelta(days=99))
        self.assertEqual(self.run_cycle()["cancelled"], 0)

    def test_dry_run_changes_nothing(self):
        from exchanges.services import process_lifecycle
        ex = services.request_book(self.book().pk, self.taker)
        self.age(ex, 30)
        self.assertEqual(process_lifecycle(dry_run=True)["cancelled"], 1)
        ex.refresh_from_db()
        self.assertEqual(ex.status, Exchange.Status.REQUESTED)

    def test_command_runs(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("expire_exchanges", "--dry-run", stdout=out)
        self.assertIn("آزمایشی", out.getvalue())

    def test_user_dispute_and_admin_resolutions(self):
        ex = services.request_book(self.book().pk, self.taker)
        with self.assertRaises(services.ExchangeError):
            services.open_dispute(ex.pk, self.taker, "other")  # هنوز تأیید نشده
        services.accept(ex.pk, self.giver)
        self.client.login(username="taker", password="x12345678")
        r = self.client.post(reverse("exchanges:dispute", args=[ex.pk]), {"reason": "no_show", "description": "نیومد"})
        self.assertEqual(r.status_code, 302)
        ex.refresh_from_db(); self.assertIsNotNone(ex.disputed_at)
        self.assertIn("اختلاف", Report.objects.get().description)
        with self.assertRaises(services.ExchangeError):
            services.open_dispute(ex.pk, self.giver, "other")  # دوباره نه
        boss = User.objects.create_superuser("boss", password="x12345678")
        services.resolve_dispute(ex.pk, boss, "complete")
        ex.refresh_from_db(); self.giver.refresh_from_db()
        self.assertEqual((ex.status, self.giver.points, ex.resolution_note), (Exchange.Status.COMPLETED, 1, "تکمیل توسط boss"))
        with self.assertRaises(services.ExchangeError):
            services.resolve_dispute(ex.pk, boss, "cancel")  # دیگه بازی نیست

    def test_admin_cancel_resolution_refunds(self):
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        services.open_dispute(ex.pk, self.giver, "no_show", "")
        boss = User.objects.create_superuser("boss", password="x12345678")
        services.resolve_dispute(ex.pk, boss, "cancel")
        ex.refresh_from_db(); ex.book.refresh_from_db(); self.taker.refresh_from_db()
        self.assertEqual((ex.status, ex.book.status, self.taker.points), (Exchange.Status.CANCELLED, Book.Status.AVAILABLE, 1))
        self.assertEqual(ex.resolution_note, "لغو توسط boss")

    def test_third_party_cannot_dispute_and_admin_actions_render(self):
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        st = User.objects.create_user("st", password="x12345678")
        with self.assertRaises(services.ExchangeError):
            services.open_dispute(ex.pk, st, "other")
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        r = self.client.post("/admin/exchanges/exchange/", {"action": "force_cancel", "_selected_action": [ex.pk]}, follow=True)
        self.assertContains(r, "اختلاف بازی نداره")  # اختلافی ثبت نشده بود
        self.assertEqual(self.client.get("/admin/exchanges/exchange/?disputed_at__isempty=0").status_code, 200)
        self.assertEqual(self.client.get("/panel/").status_code, 200)


import json
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

_MEDIA = tempfile.mkdtemp(prefix="hv-media-")


def _jpeg(w=3000, h=2000, exif=True, fmt="JPEG", mode="RGB"):
    import io
    from PIL import Image
    img = Image.new(mode, (w, h), (200, 30, 30) if mode == "RGB" else (200, 30, 30, 0))
    buf = io.BytesIO()
    kwargs = {}
    if exif:
        ex = Image.Exif()
        ex[0x0112] = 6                       # چرخش ۹۰ درجه
        ex[0x010F] = "SecretCamera"          # سازنده‌ی دوربین
        ex.get_ifd(0x8825)[1] = "N"          # GPS
        kwargs["exif"] = ex
    img.save(buf, fmt, **kwargs)
    return SimpleUploadedFile("p." + fmt.lower(), buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(MEDIA_ROOT=_MEDIA)
class PhotoTests(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def post_book(self, **files):
        self.client.login(username="giver", password="x12345678")
        data = {"title": "عکسی", "author": "ن", "condition": "used", "city": self.isfahan.pk, **files}
        return self.client.post(reverse("books:create"), data)

    def test_cover_stripped_resized_rotated_with_thumb(self):
        from PIL import Image
        r = self.post_book(cover=_jpeg())
        self.assertEqual(r.status_code, 302)
        b = Book.objects.get(title="عکسی")
        with Image.open(b.cover.path) as im:
            self.assertEqual(len(im.getexif()), 0)               # EXIF (GPS و دوربین) پاک شده
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), 1280)
            self.assertGreater(im.height, im.width)              # چرخش اعمال شد (۳۰۰۰×۲۰۰۰ ← عمودی)
        with Image.open(b.cover_thumb.path) as th:
            self.assertLessEqual(max(th.size), 420)
        self.assertTrue(b.thumb_url.endswith(".jpg"))
        self.assertNotEqual(b.thumb_url, b.cover.url)

    def test_extra_photos_limit_and_delete(self):
        self.post_book(cover=_jpeg(800, 600), extra_photos=[_jpeg(500, 500), _jpeg(500, 500)])
        b = Book.objects.get(title="عکسی")
        self.assertEqual(b.photos.count(), 2)
        self.assertContains(self.client.get(reverse("books:detail", args=[b.pk])), "data-gallery-thumb")
        # سقف ۴ عکس اضافه (۲ تا هست، ۳ تا دیگه نمی‌شه)
        r = self.client.post(reverse("books:edit", args=[b.pk]), {
            "title": "عکسی", "author": "ن", "condition": "used", "city": self.isfahan.pk,
            "extra_photos": [_jpeg(300, 300), _jpeg(300, 300), _jpeg(300, 300)]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b.photos.count(), 2)
        photo = b.photos.first()
        path = photo.image.path
        self.client.login(username="taker", password="x12345678")
        self.assertEqual(self.client.post(reverse("books:photo_delete", args=[photo.pk])).status_code, 404)  # مال کس دیگه‌ست
        self.client.login(username="giver", password="x12345678")
        self.client.post(reverse("books:photo_delete", args=[photo.pk]))
        self.assertEqual(b.photos.count(), 1)
        import os
        self.assertFalse(os.path.exists(path))

    def test_edit_keeps_cover_when_not_replaced(self):
        self.post_book(cover=_jpeg(800, 600))
        b = Book.objects.get(title="عکسی")
        old = b.cover.name
        self.client.post(reverse("books:edit", args=[b.pk]), {
            "title": "عنوان نو", "author": "ن", "condition": "used", "city": self.isfahan.pk})
        b.refresh_from_db()
        self.assertEqual((b.title, b.cover.name), ("عنوان نو", old))

    def test_bad_and_huge_files_rejected(self):
        bad = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.post_book(cover=bad).status_code, 200)
        self.assertFalse(Book.objects.filter(title="عکسی").exists())
        big = SimpleUploadedFile("big.jpg", b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 10), content_type="image/jpeg")
        self.assertEqual(self.post_book(cover=big).status_code, 200)
        self.assertFalse(Book.objects.filter(title="عکسی").exists())

    def test_png_with_transparency_becomes_white_jpeg(self):
        from PIL import Image
        self.post_book(cover=_jpeg(400, 400, exif=False, fmt="PNG", mode="RGBA"))
        b = Book.objects.get(title="عکسی")
        with Image.open(b.cover.path) as im:
            self.assertEqual(im.format, "JPEG")
            r, g, bl = im.getpixel((5, 5))
            self.assertGreater(min(r, g, bl), 240)  # شفاف ← سفید

    def test_report_image_processed(self):
        from PIL import Image
        self.client.login(username="taker", password="x12345678")
        b = self.book()
        self.client.post(reverse("trust:report", args=["book", b.pk]), {"reason": "bad_book", "image": _jpeg(2000, 1500)})
        rep = Report.objects.get()
        with Image.open(rep.image.path) as im:
            self.assertEqual(len(im.getexif()), 0)
            self.assertLessEqual(max(im.size), 1280)


class InfraTests(Base):
    def test_backup_sqlite_copies_real_data(self):
        import os, sqlite3
        from common.management.commands.backup_db import backup_sqlite
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "live.sqlite3")
            conn = sqlite3.connect(src)
            conn.execute("create table t (v text)"); conn.execute("insert into t values ('سلام')"); conn.commit(); conn.close()
            out = os.path.join(d, "backup.sqlite3")
            backup_sqlite(src, out)
            c = sqlite3.connect(out)
            self.assertEqual(c.execute("select v from t").fetchone()[0], "سلام")
            c.close()

    def test_backup_command_prunes_old_and_archives_media(self):
        import os, time
        from io import StringIO
        from unittest import mock
        from django.core.management import call_command

        def fake_backup(name, target):
            open(target, "w").write("db")

        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as media:
            open(os.path.join(media, "a.txt"), "w").write("x")
            with override_settings(BACKUP_KEEP=2, MEDIA_ROOT=media), \
                    mock.patch("common.management.commands.backup_db.backup_sqlite", fake_backup):
                for _ in range(3):
                    out = StringIO()
                    call_command("backup_db", "--media", "--dir", d, stdout=out)
                    time.sleep(1.1)  # مهر زمانی نام فایل‌ها یکتا بشه
            names = os.listdir(d)
            self.assertEqual(len([n for n in names if n.startswith("db-")]), 2)     # قدیمی‌ترین حذف شد
            self.assertEqual(len([n for n in names if n.startswith("media-")]), 2)
            self.assertIn("حذف بکاپ قدیمی", out.getvalue())

    def test_logging_configured_and_sentry_off_in_tests(self):
        from django.conf import settings
        self.assertIn("console", settings.LOGGING["root"]["handlers"])
        import sentry_sdk
        self.assertFalse(sentry_sdk.is_initialized())

    def test_sentry_init_does_not_send_pii(self):
        # ایمپورت کتابخونه سالمه و تنظیمات ما کلید حساسی نمی‌گیره
        import inspect
        from pathlib import Path
        src = Path(inspect.getfile(self.__class__)).parent.parent / "HamVaraqDjangoServer" / "settings.py"
        self.assertIn("send_default_pii=False", src.read_text(encoding="utf-8"))


class WelcomePointsTests(Base):
    def signup(self, name, ip="8.8.8.8"):
        from django.core.cache import cache
        cache.clear()
        from django.test import Client
        c = Client()
        c.post(reverse("accounts:signup"), {
            "username": name, "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99", "city": self.tehran.pk,
            "accept_rules": "on"},
            REMOTE_ADDR=ip)
        return User.objects.get(username=name), c

    def test_ip_hash_is_not_raw_and_private_ips_skipped(self):
        u, _ = self.signup("a1", "8.8.8.8")
        self.assertEqual(len(u.signup_ip_hash), 64)
        self.assertNotIn("8.8.8.8", u.signup_ip_hash)
        self.assertEqual(u.signup_ip_hash, u.last_ip_hash)
        p, _ = self.signup("a2", "192.168.1.5")
        self.assertEqual((p.signup_ip_hash, p.points), ("", 1))  # آی‌پی خصوصی: بدون شمارش ولی هدیه می‌گیره

    def test_welcome_cap_per_network_then_zero(self):
        got = [self.signup(f"u{i}")[0].points for i in range(7)]
        self.assertEqual(got, [1, 1, 1, 1, 1, 0, 0])  # سقف ۵ حساب هدیه برای هر شبکه
        other, _ = self.signup("elsewhere", "9.9.9.9")
        self.assertEqual(other.points, 1)               # شبکه‌ی دیگه آزاده

    def test_window_expires_and_setting_off(self):
        from django.test import override_settings
        for i in range(5):
            self.signup(f"w{i}")
        User.objects.update(date_joined=timezone.now() - timedelta(days=31))
        self.assertEqual(self.signup("late")[0].points, 1)  # بازه‌ی ۳۰ روزه گذشته
        with override_settings(WELCOME_POINTS=0):
            self.assertEqual(self.signup("none", "7.7.7.7")[0].points, 0)

    def test_ipv6_grouped_by_64(self):
        a, _ = self.signup("v6a", "2606:4700:1:2::1")
        b, _ = self.signup("v6b", "2606:4700:1:2:ffff::9")
        self.assertEqual(a.signup_ip_hash, b.signup_ip_hash)
        c, _ = self.signup("v6c", "2606:4700:1:3::1")
        self.assertNotEqual(a.signup_ip_hash, c.signup_ip_hash)

    def test_login_updates_last_network(self):
        u, _ = self.signup("mover", "8.8.8.8")
        from django.test import Client
        Client().post(reverse("accounts:login"), {"username": "mover", "password": "Str0ng-pass-99"}, REMOTE_ADDR="9.9.9.9")
        u.refresh_from_db()
        self.assertNotEqual(u.last_ip_hash, u.signup_ip_hash)

    def test_new_user_can_request_immediately_with_welcome_point(self):
        newbie, client = self.signup("fresh", "8.8.8.8")
        book = self.book()
        client.post(reverse("exchanges:request", args=[book.pk]), REMOTE_ADDR="8.8.8.8")
        self.assertTrue(Exchange.objects.filter(book=book, requester=newbie).exists())
        newbie.refresh_from_db()
        self.assertEqual(newbie.points, 0)

    def test_linked_newcomer_cannot_drain_same_network_account(self):
        owner, _ = self.signup("main", "8.8.8.8")
        fake, _ = self.signup("fake", "8.8.8.8")   # هم‌شبکه
        book = Book.objects.create(owner=owner, title="هدف", author="ن", city=self.tehran)
        with self.assertRaises(services.ExchangeError) as cm:
            services.request_book(book.pk, fake)
        self.assertIn("همین شبکه", str(cm.exception))
        # از حساب شبکه‌ی دیگه آزاده
        stranger, _ = self.signup("stranger", "9.9.9.9")
        self.assertIsNotNone(services.request_book(book.pk, stranger))

    def test_linked_user_allowed_after_giving_someone_else(self):
        owner, _ = self.signup("main", "8.8.8.8")
        friend, _ = self.signup("friend", "8.8.8.8")
        far, _ = self.signup("far", "9.9.9.9")
        mine = Book.objects.create(owner=friend, title="کتاب دوست", author="ن", city=self.tehran)
        ex = services.request_book(mine.pk, far)
        services.accept(ex.pk, friend); services.confirm(ex.pk, friend); services.confirm(ex.pk, far)
        target = Book.objects.create(owner=owner, title="هدف", author="ن", city=self.tehran)
        self.assertIsNotNone(services.request_book(target.pk, friend))  # حالا کتاب داده، پس آزاد

    def test_dashboard_flags_shared_network_groups_and_admin_renders(self):
        for i in range(3):
            self.signup(f"g{i}", "8.8.8.8")
        from common.stats import collect
        flagged = {u.username for u, why in collect()["suspicious"] if any("از یه شبکه" in w for w in why)}
        self.assertEqual(flagged, {"g0", "g1", "g2"})
        boss = User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        r = self.client.get(reverse("admin:accounts_user_change", args=[boss.pk]))
        self.assertContains(r, "شناسه‌ی شبکه")


class GuideTests(Base):
    def test_pages_render_with_real_settings_values(self):
        r = self.client.get(reverse("how_it_works"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "۷ روز")   # REQUEST_EXPIRE_DAYS
        self.assertContains(r, "۲۱ روز")  # ACCEPTED_EXPIRE_DAYS
        self.assertContains(r, "۲۴ ساعت")  # VOTE_EDIT_HOURS
        self.assertContains(r, 'id="safety"')
        self.assertContains(self.client.get(reverse("rules")), "۱۴ روز")  # RESTRICTION_DAYS
        self.assertNotContains(r, "شروع سریع")  # مهمان چک‌لیست نمی‌بینه

    def test_numbers_in_guide_follow_settings(self):
        from django.test import override_settings
        with override_settings(REQUEST_EXPIRE_DAYS=10):
            self.assertContains(self.client.get(reverse("how_it_works")), "۱۰ روز")

    def test_signup_requires_accepting_rules(self):
        from django.core.cache import cache
        cache.clear()
        data = {"username": "norules", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99", "city": self.tehran.pk}
        r = self.client.post(reverse("accounts:signup"), data)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="norules").exists())
        self.assertContains(r, "قوانین")
        self.assertContains(self.client.get(reverse("accounts:signup")), reverse("rules"))

    @override_settings(WISHLIST_ENABLED=True)
    def test_onboarding_steps_follow_real_progress(self):
        from common.onboarding import progress
        u = User.objects.create_user("newbie", password="x12345678", points=1)
        p = progress(u)
        self.assertEqual((p["done"], p["total"], p["complete"]), (0, 5, False))
        u.city = self.tehran; u.save()
        book = self.book()
        services.request_book(book.pk, u)
        Wishlist.objects.create(user=u, text="x")
        done = [s["done"] for s in progress(u)["steps"]]
        self.assertEqual(done, [True, False, True, False, True])
        # دادن کتاب + مبادله‌ی کامل
        Book.objects.create(owner=u, title="مال من", author="ن", city=self.tehran)
        ex = Exchange.objects.get(requester=u)
        services.accept(ex.pk, self.giver); services.confirm(ex.pk, self.giver); services.confirm(ex.pk, u)
        self.assertTrue(progress(u)["complete"])

    def test_home_shows_checklist_for_members_and_hero_for_guests(self):
        guest = self.client.get("/")
        self.assertContains(guest, "هم‌ورق شو")
        self.assertNotContains(guest, "شروع سریع")
        self.client.login(username="giver", password="x12345678")
        home = self.client.get("/")
        self.assertContains(home, "شروع سریع")
        self.assertIsNotNone(home.context["onboarding"])

    def test_guide_in_nav_footer_sitemap_and_help_in_exchange(self):
        page = self.client.get("/").content.decode()
        self.assertIn(reverse("how_it_works"), page)
        self.assertIn(reverse("rules"), page)
        sm = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/how-it-works/", sm); self.assertIn("/rules/", sm)
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        self.client.login(username="taker", password="x12345678")
        self.assertContains(self.client.get(reverse("exchanges:detail", args=[ex.pk])), "how-it-works/#safety")

    def test_empty_search_suggests_next_steps(self):
        self.client.login(username="giver", password="x12345678")
        r = self.client.get(reverse("books:list"), {"q": "چیزی که نیست"})
        self.assertContains(r, "لیست آرزو")


class ChatPrivacyTests(Base):
    def test_admin_sees_chat_only_for_disputed_or_reported(self):
        from exchanges.models import Message
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        msg = Message.objects.create(exchange=ex, sender=self.taker, text="متن‌خصوصی‌۱۲۳")
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        url = reverse("admin:exchanges_exchange_change", args=[ex.pk])
        self.assertNotContains(self.client.get(url), "متن‌خصوصی‌۱۲۳")          # عادی: چت پنهانه
        Report.objects.create(reporter=self.giver, target_message=msg, reason="abuse")
        self.assertContains(self.client.get(url), "متن‌خصوصی‌۱۲۳")             # گزارش روی پیام: دیده می‌شه
        User.objects.filter(pk=self.taker.pk).update(points=1)
        self.taker.refresh_from_db()
        ex2 = services.request_book(self.book(title="دیگری").pk, self.taker)
        services.accept(ex2.pk, self.giver)
        Message.objects.create(exchange=ex2, sender=self.taker, text="پیام‌دوم‌۴۵۶")
        url2 = reverse("admin:exchanges_exchange_change", args=[ex2.pk])
        self.assertNotContains(self.client.get(url2), "پیام‌دوم‌۴۵۶")
        services.open_dispute(ex2.pk, self.taker, "other")
        self.assertContains(self.client.get(url2), "پیام‌دوم‌۴۵۶")              # اختلاف: دیده می‌شه


class PersianFormsTests(Base):
    def test_no_english_empty_choice_and_autocomplete_attrs(self):
        import re
        self.client.login(username="giver", password="x12345678")
        ex_done = self.complete(self.book(title="تمام"))
        User.objects.filter(pk=self.taker.pk).update(points=1)
        self.taker.refresh_from_db()
        ex = services.request_book(self.book().pk, self.taker)
        services.accept(ex.pk, self.giver)
        pages = ["/accounts/signup/", "/accounts/settings/", "/books/new/", "/books/bulk/", "/books/",
                 f"/exchanges/{ex.pk}/", f"/exchanges/{ex_done.pk}/", f"/trust/report/book/{self.book(title='گزارش').pk}/"]
        for url in pages:
            html = self.client.get(url).content.decode()
            self.assertNotIn("Select an option", html, url)
            self.assertNotIn("---------", html, url)
            visible = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
            for attr in re.findall(r'(?:placeholder|title|alt|aria-label)="([^"]*)"', visible):
                self.assertNotRegex(attr, "[A-Za-z]{3,}", f"{url}: {attr}")
        self.client.logout()
        html = self.client.get("/accounts/signup/").content.decode()
        self.assertIn('autocomplete="username"', html)
        self.assertEqual(html.count('autocomplete="new-password"'), 2)
        self.assertIn('autocomplete="email"', html)
        self.assertNotRegex(html.split('id="signup-form"')[1].split("</form>")[0], r"characters|Letters|digits")
        self.assertIn('autocomplete="current-password"', self.client.get("/accounts/login/").content.decode())

    def test_admin_app_names_are_persian(self):
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        html = self.client.get("/admin/").content.decode()
        for name in ("حساب‌ها", "مبادله‌ها", "اعتماد و ایمنی"):
            self.assertIn(name, html)
        self.assertIn("مدیریت هم‌ورق", html)

    def test_favicon_redirects(self):
        r = self.client.get("/favicon.ico")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].endswith("/static/favicon.svg"))


class LocationTests(Base):
    def test_clean_locations_rules(self):
        from common.locations import clean_locations
        raw = {"تبریز ": ["تبریز", "تبریز1", "تبریز2", "علی  آباد", "بندر عباس", "كاشان", "کاشان", "  "], "": ["x"]}
        out = clean_locations(raw)
        self.assertEqual(list(out), ["تبریز"])
        self.assertEqual(out["تبریز"], sorted(["تبریز", "علی آباد", "بندرعباس", "کاشان"]))
        self.assertEqual(clean_locations(out), out)  # idempotent

    def test_shipped_data_is_clean_and_complete(self):
        from common.locations import load_locations
        data = load_locations()
        self.assertEqual(len(data), 31)
        self.assertGreater(sum(len(v) for v in data.values()), 1400)
        for province, cities in data.items():
            for name in cities:
                self.assertNotRegex(name, r"\d")
                self.assertEqual(name, " ".join(name.split()))
        for p, c in (("تهران", "تهران"), ("اصفهان", "اصفهان"), ("خراسان رضوی", "مشهد"), ("فارس", "شیراز"), ("هرمزگان", "بندرعباس"),
                     ("آذربایجان شرقی", "تبریز"), ("قم", "قم"), ("خوزستان", "اهواز")):
            self.assertIn(c, data[p], (p, c))

    def test_seed_command_idempotent_and_no_duplicates_of_existing(self):
        from io import StringIO
        from django.core.management import call_command
        existing = make_city("بندر عباس", "هرمزگان")  # املای قدیمی
        out = StringIO()
        call_command("seed_iran_locations", stdout=out)
        n = City.objects.count()
        call_command("seed_iran_locations", stdout=StringIO())
        self.assertEqual(City.objects.count(), n)
        self.assertEqual(City.objects.filter(province__name="هرمزگان", name__in=["بندر عباس", "بندرعباس"]).count(), 1)
        self.assertTrue(City.objects.filter(pk=existing.pk).exists())
        self.assertEqual(Province.objects.count(), 31)  # استان‌های آزمایشی هم جزو همین ۳۱ تا هستن


class LocationFormTests(Base):
    def book_data(self, **kw):
        return {"title": "الف", "author": "ب", "condition": "used", **kw}

    def test_signup_has_no_location_fields(self):
        html = self.client.get(reverse("accounts:signup")).content.decode()
        self.assertNotIn('name="city"', html)
        self.assertNotIn('name="province"', html)

    def test_book_form_requires_city_matching_province(self):
        from books.forms import BookForm
        self.assertIn("city", BookForm(data=self.book_data()).errors)                      # شهر اجباری
        bad = BookForm(data=self.book_data(province=self.tehran.province_id, city=self.isfahan.pk))
        self.assertFalse(bad.is_valid())
        self.assertIn("city", bad.errors)                                                   # نامربوط
        ok = BookForm(data=self.book_data(city=self.isfahan.pk))                            # استان از شهر مشخص می‌شه
        self.assertTrue(ok.is_valid(), ok.errors)
        self.assertEqual(ok.cleaned_data["province"], self.isfahan.province)

    def test_book_create_view_saves_city_and_defaults_to_profile_or_last_city(self):
        self.client.login(username="giver", password="x12345678")
        self.giver.city = None; self.giver.save()
        page = self.client.get(reverse("books:create"))
        self.assertIsNone(page.context["form"].initial.get("city"))
        self.client.post(reverse("books:create"), self.book_data(province=self.tehran.province_id, city=self.tehran.pk))
        self.assertEqual(Book.objects.get().city, self.tehran)
        page = self.client.get(reverse("books:create"))
        self.assertEqual(page.context["form"].initial["city"], self.tehran.pk)              # آخرین شهر
        self.giver.city = self.isfahan; self.giver.save()
        page = self.client.get(reverse("books:create"))
        self.assertEqual(page.context["form"].initial["city"], self.isfahan.pk)            # پروفایل مقدم

    def test_options_carry_province_for_cascade(self):
        self.client.login(username="giver", password="x12345678")
        html = self.client.get(reverse("books:create")).content.decode()
        self.assertIn(f'data-province="{self.tehran.province_id}"', html)
        self.assertIn('data-location="province"', html)
        self.assertIn("اصفهان، اصفهان", html)  # بدون JS هم «شهر، استان»

    def test_profile_location_optional_and_validated(self):
        self.client.login(username="giver", password="x12345678")
        url = reverse("accounts:settings")
        self.assertEqual(self.client.post(url, {"email": ""}).status_code, 302)             # هیچ‌کدوم: اوکی
        r = self.client.post(url, {"province": self.tehran.province_id, "city": ""})
        self.assertEqual(r.status_code, 200)                                                # استان بی‌شهر: خطا
        self.client.post(url, {"city": self.tehran.pk})
        self.giver.refresh_from_db(); self.assertEqual(self.giver.city, self.tehran)
        self.client.post(url, {"email": ""})
        self.giver.refresh_from_db(); self.assertIsNone(self.giver.city)                    # پاک شد

    def test_list_filter_by_province_city_and_mismatch(self):
        a = self.book(title="اصفهانی")
        Book.objects.create(owner=self.giver, title="تهرانی", author="ن", city=self.tehran)
        names = lambda r: sorted(b.title for b in r.context["page"])
        get = lambda **q: self.client.get(reverse("books:list"), q)
        self.assertEqual(names(get(province=self.tehran.province_id)), ["تهرانی"])
        self.assertEqual(names(get(city=self.isfahan.pk)), ["اصفهانی"])                     # فقط شهر هم کافیه
        self.assertEqual(names(get(province=self.tehran.province_id, city=self.tehran.pk)), ["تهرانی"])
        # لینک دستکاری‌شده: شهر نامربوط نادیده گرفته می‌شه و استان فیلتر می‌کنه
        self.assertEqual(names(get(province=self.tehran.province_id, city=self.isfahan.pk)), ["تهرانی"])
        self.assertEqual(a.city.full_name, "اصفهان، اصفهان")

    def test_relist_fills_unknown_journey_destination(self):
        taker = User.objects.create_user("nocity", password="x12345678", points=1)  # شهر نداره
        ex = self.complete(self.book(), taker)
        step = ex.book.journey.get(); self.assertIsNone(step.to_city)
        self.client.login(username="nocity", password="x12345678")
        self.client.post(reverse("books:relist", args=[ex.book.pk]), {"city": self.tehran.pk})
        step.refresh_from_db(); self.assertEqual(step.to_city, self.tehran)


def visible_text(html):
    """متن دیده‌شده‌ی صفحه + مقدار صفات کاربرمحور (placeholder، title، alt، aria-label، value دکمه‌ها)."""
    import re
    from html import unescape
    html = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    attrs = re.findall(r'\b(?:placeholder|title|alt|aria-label|aria-description)="([^"]*)"', html)
    attrs += re.findall(r'<input[^>]+type="(?:submit|button)"[^>]*\bvalue="([^"]*)"', html)
    head_title = re.findall(r"<title>(.*?)</title>", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    return unescape(" ".join([text, *attrs, *head_title]))


class NoEnglishAuditTests(TestCase):
    """هیچ کلمه‌ی انگلیسی تو متن دیده‌شده‌ی صفحه‌ها، فرم‌ها و ادمین نباشه (داده‌ی کاربر فارسیه)."""

    ALLOWED = ("hamvaraq.ir",)
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        import tempfile
        cls.tehran = make_city("تهران")
        cls.cat = Category.objects.create(name="رمان")
        cls.a = User.objects.create_user("سارا", password="x12345678", city=cls.tehran, points=3)
        cls.b = User.objects.create_user("علی", password="x12345678", city=cls.tehran, points=3)
        cls.boss = User.objects.create_superuser("مدیر", password="x12345678")
        cls.book = Book.objects.create(owner=cls.a, title="بوف کور", author="صادق هدایت", city=cls.tehran, category=cls.cat)
        cls.b2 = Book.objects.create(owner=cls.b, title="کلیدر", author="دولت‌آبادی", city=cls.tehran, category=cls.cat)
        from common.models import MeetingPoint
        MeetingPoint.objects.create(city=cls.tehran, name="مترو شریعتی", kind="metro")
        cls.ex = services.request_book(cls.book.pk, cls.b)
        services.accept(cls.ex.pk, cls.a)
        cls.done = None
        cls._tmp = tempfile.mkdtemp()

    def check(self, urls, label):
        import re
        bad = []
        for url in urls:
            r = self.client.get(url, follow=True)
            self.assertLess(r.status_code, 400, url)
            text = visible_text(r.content.decode())
            for allowed in self.ALLOWED:
                text = text.replace(allowed, "")
            words = re.findall(r"[A-Za-z][A-Za-z'\-]+", text)
            if words:
                bad.append((url, sorted(set(words))[:8]))
        self.assertEqual(bad, [], f"{label}: کلمه‌ی انگلیسی پیدا شد")

    def test_guest_pages(self):
        self.check(["/", "/books/", "/books/?q=بوف", f"/books/{self.book.pk}/", "/cities/", f"/cities/{self.tehran.pk}/",
                   f"/provinces/{self.tehran.province_id}/", "/authors/", "/authors/%D8%B5%D8%A7%D8%AF%D9%82-%D9%87%D8%AF%D8%A7%DB%8C%D8%AA/", "/publishers/", "/challenges/", "/how-it-works/", "/rules/", "/accounts/login/",
                   "/accounts/signup/", "/accounts/password-reset/", "/offline/", "/accounts/u/سارا/"], "مهمان")

    def test_member_pages(self):
        self.client.login(username="علی", password="x12345678")
        self.check(["/", "/books/new/", "/books/bulk/", "/books/mine/", "/books/wishlist/", "/exchanges/",
                    f"/exchanges/{self.ex.pk}/", "/notifications/", "/accounts/settings/",
                    f"/trust/report/book/{self.book.pk}/", f"/trust/report/user/{self.a.pk}/"], "عضو")

    def test_admin_pages(self):
        self.client.login(username="مدیر", password="x12345678")
        urls = ["/admin/", "/staff/"]
        for model in ("accounts/user", "accounts/badge", "accounts/userbadge", "books/book", "books/category", "books/review",
                      "books/wishlist", "books/booknote", "books/bookjourney", "challenges/challenge", "common/city",
                      "common/province", "common/meetingpoint", "common/sitesetting", "exchanges/exchange", "notifications/notification",
                      "trust/report", "trust/vote", "books/edition", "posts/post", "posts/tag", "announcements/announcement", "announcements/announcementbookmark",
                      "notifications/pushsubscription", "notifications/notificationpreference"):
            urls += [f"/admin/{model}/"] + ([] if model == "common/sitesetting" else [f"/admin/{model}/add/"])
        urls.append("/admin/common/sitesetting/1/change/")
        self.check(urls, "ادمین")

    def test_support_and_panel_pages(self):
        from support.models import Ticket
        from trust.models import Report
        t = Ticket.objects.create(user=self.a, subject="مشکل", message="پیام کافی برای تست", reply="پاسخ")
        r = Report.objects.create(reporter=self.a, target_user=self.b, reason="abuse", description="توهین")
        self.client.login(username="سارا", password="x12345678")
        self.check(["/support/", "/support/?type=bug&from=/books/", "/support/mine/", t.get_absolute_url(), "/accounts/stats/", "/accounts/delete/"], "عضو پشتیبانی")
        self.client.login(username="مدیر", password="x12345678")
        self.check(["/panel/", "/panel/reports/", f"/panel/reports/{r.pk}/", "/panel/tickets/", f"/panel/tickets/{t.pk}/", "/panel/exchanges/",
                    "/panel/users/", f"/panel/users/{self.b.pk}/", "/panel/books/", "/panel/posts/", "/panel/announcements/", "/panel/challenges/",
                    "/panel/challenges/new/", "/panel/settings/", "/panel/audit/", "/panel/stats/", "/panel/stats/?days=7", "/admin/support/ticket/", "/admin/common/auditlog/"], "پنل")

    def test_posts_and_announcements_pages(self):
        from posts.models import Post
        from announcements.models import Announcement
        from announcements import services as asv
        post = Post.objects.create(author=self.a, book=self.book, title="معرفی بوف کور", body="متن " * 60, status="published", published_at=timezone.now())
        ev = Announcement(title="رونمایی کتاب", summary="خلاصه", kind="launch", city=self.tehran, venue="خانه‌ی کتاب",
                          starts_at=timezone.now() + timezone.timedelta(days=3))
        asv.submit(ev, self.boss)
        urls = ["/posts/", post.get_absolute_url(), "/announcements/", "/announcements/?tab=past", ev.get_absolute_url(),
                "/posts/by/سارا/"]
        self.check(urls, "مهمان محتوا")
        self.client.login(username="سارا", password="x12345678")
        self.check(urls + ["/posts/new/", f"{post.get_absolute_url()}edit/", "/posts/mine/", "/announcements/new/", "/announcements/mine/"], "عضو محتوا")

    def test_completed_exchange_and_vote_pages(self):
        ex = services.request_book(self.b2.pk, self.a)
        services.accept(ex.pk, self.b); services.confirm(ex.pk, self.b); services.confirm(ex.pk, self.a)
        self.client.login(username="سارا", password="x12345678")
        self.check([f"/exchanges/{ex.pk}/", f"/books/{self.b2.pk}/", f"/books/{self.b2.pk}/relist/"], "مبادله‌ی کامل")


class SuggestAndSettingsTests(Base):
    def test_suggest_titles_authors_and_limits(self):
        self.book(title="بوف کور"); Book.objects.create(owner=self.giver, title="بوف‌کور دوم", author="هدایت", city=self.isfahan)
        r = self.client.get(reverse("books:suggest"), {"kind": "title", "q": "كور"})  # ک عربی هم کار می‌کنه
        self.assertEqual(len(r.json()["items"]), 2)
        self.assertEqual(self.client.get(reverse("books:suggest"), {"q": "ب"}).json(), {"items": []})  # خیلی کوتاه
        self.assertEqual(self.client.get(reverse("books:suggest"), {"kind": "author", "q": "هدا"}).json(), {"items": [{"author": "هدایت"}]})
        self.assertEqual(self.client.get(reverse("books:suggest"), {"q": "ناموجود"}).json(), {"items": []})

    def test_quick_search_books_and_limits(self):
        self.book(title="بوف کور"); Book.objects.create(owner=self.giver, title="کلیدر", author="دولت‌آبادی", city=self.isfahan)
        d = self.client.get(reverse("books:quick"), {"q": "كور"}).json()  # ک عربی هم پیدا می‌شه
        self.assertEqual([b["title"] for b in d["books"]], ["بوف کور"])
        self.assertEqual(d["total"], 1)
        self.assertEqual(self.client.get(reverse("books:quick"), {"q": "ب"}).json(), {"books": [], "posts": [], "total": 0})
        self.assertEqual(self.client.get(reverse("books:quick"), {"q": "ناموجود"}).json()["total"], 0)

    def test_search_dialog_is_in_every_page(self):
        r = self.client.get("/")
        self.assertContains(r, 'id="search-dialog"')
        self.assertContains(r, "data-search-open")
        self.assertContains(r, reverse("books:quick"))

    def test_form_wires_suggest_attributes(self):
        self.client.login(username="giver", password="x12345678")
        html = self.client.get(reverse("books:create")).content.decode()
        self.assertIn('data-suggest="title"', html)
        self.assertIn('data-suggest="author"', html)
        self.assertIn(reverse("books:suggest"), html)

    def test_site_setting_singleton_defaults_and_context(self):
        from common.models import SiteSetting
        s = SiteSetting.load()
        self.assertEqual(s.pk, 1)
        self.assertIn("بخوان", s.tagline)
        s2 = SiteSetting(tagline="شعار تازه"); s2.save()
        self.assertEqual(SiteSetting.objects.count(), 1)
        self.assertEqual(SiteSetting.load().tagline, "شعار تازه")  # کش بعد از ذخیره پاک می‌شه
        r = self.client.get("/")
        self.assertEqual(r.context["site"].tagline, "شعار تازه")

    def test_translations_override_django_english(self):
        from django.utils.translation import gettext
        self.assertEqual(gettext("- Select an option -"), "انتخاب کنید")
        self.assertEqual(gettext("Breadcrumbs"), "مسیر صفحه")


class LandingAndHomeTests(Base):
    def test_guest_landing_sections_and_real_stats(self):
        self.book()
        self.complete(self.book(title="دوم"))
        r = self.client.get("/")
        self.assertTemplateUsed(r, "landing.html")
        self.assertEqual((r.context["stats"]["books"], r.context["stats"]["exchanges"]), (2, 1))
        html = r.content.decode()
        for needle in ("چطور کار می‌کنه؟", "تازه‌رسیده‌ها", "سوال‌های پرتکرار", "هم‌ورق شو", "chip", "ill-hero"):
            self.assertIn(needle, html)
        self.assertEqual(html.count("<details class=\"faq\">"), 6)

    def test_landing_structured_data_valid_json_and_escaped(self):
        import json, re
        html = self.client.get("/").content.decode()
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, flags=re.S)
        self.assertEqual(len(blocks), 2)
        faq, site = (json.loads(b) for b in blocks)
        self.assertEqual(faq["@type"], "FAQPage")
        self.assertEqual(len(faq["mainEntity"]), 6)
        self.assertEqual(site["potentialAction"]["@type"], "SearchAction")

    def test_landing_uses_site_settings_texts(self):
        from common.models import SiteSetting
        SiteSetting(hero_title="تیتر دلخواه من", cta_title="بپیوند", telegram_url="https://t.me/x").save()
        html = self.client.get("/").content.decode()
        self.assertIn("تیتر دلخواه من", html)
        self.assertIn("بپیوند", html)
        self.assertIn("https://t.me/x", html)  # فوتر

    def test_landing_hides_empty_sections(self):
        html = self.client.get("/").content.decode()
        self.assertNotIn("تازه‌رسیده‌ها", html)
        self.assertNotIn("تو کدوم شهری؟", html)

    @override_settings(WISHLIST_ENABLED=True)
    def test_member_home_todos_wishlist_local_and_challenges(self):
        from challenges.models import Challenge
        mine = self.book(title="کتاب من")
        ex = services.request_book(mine.pk, self.taker)            # taker از giver می‌خواد
        Book.objects.create(owner=self.taker, title="کلیدر", author="دولت‌آبادی", city=self.isfahan)
        Wishlist.objects.create(user=self.giver, text="كلیدر")      # ک عربی؛ باید پیدا بشه
        Challenge.objects.create(title="چالش", kind="give", target=2, starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() + timedelta(days=5))
        self.client.login(username="giver", password="x12345678")
        r = self.client.get("/")
        self.assertTemplateUsed(r, "home.html")
        self.assertEqual([e.pk for e in r.context["waiting"]], [ex.pk])
        self.assertEqual([b.title for b in r.context["matches"]], ["کلیدر"])
        self.assertTrue(r.context["local_is_city"])                 # giver شهر داره (اصفهان)
        self.assertEqual(len(r.context["challenges"]), 1)
        self.assertContains(r, "کتاب من")
        self.assertNotContains(r, "تو کدوم شهری؟")

    def test_member_home_without_city_falls_back_to_latest(self):
        User.objects.filter(pk=self.giver.pk).update(city=None)
        self.book(owner=self.taker, title="دیگران")
        self.client.login(username="giver", password="x12345678")
        r = self.client.get("/")
        self.assertFalse(r.context["local_is_city"])
        self.assertEqual([b.title for b in r.context["local"]], ["دیگران"])
        self.assertContains(r, "شهرت رو انتخاب کن")


from unittest import mock

from django.test import override_settings
from notifications.models import NotificationPreference, PushSubscription
from notifications import push as push_mod
from notifications.services import notify

VAPID = {"VAPID_PUBLIC_KEY": "BPub", "VAPID_PRIVATE_KEY": "priv", "VAPID_SUBJECT": "mailto:a@b.c"}
SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k" * 20, "auth": "a" * 8}}


class WebPushTests(Base):
    def subscribe(self, user, endpoint="https://push.example/abc"):
        return PushSubscription.objects.create(user=user, endpoint=endpoint, p256dh="k" * 20, auth="a" * 8)

    def test_subscribe_api_validation_and_limits(self):
        url = reverse("notifications:push_subscribe")
        post = lambda body: self.client.post(url, data=json.dumps(body), content_type="application/json")
        self.assertEqual(post(SUB).status_code, 302)                          # لاگین لازمه
        self.client.login(username="giver", password="x12345678")
        with override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY=""):
            self.assertEqual(post(SUB).status_code, 503)                     # بدون کلید
        with override_settings(**VAPID):
            self.assertEqual(post({"endpoint": "http://insecure", "keys": SUB["keys"]}).status_code, 400)   # فقط https
            self.assertEqual(post({"endpoint": SUB["endpoint"], "keys": {}}).status_code, 400)
            self.assertEqual(self.client.post(url, data="not json", content_type="application/json").status_code, 400)
            r = post(SUB)
            self.assertEqual((r.status_code, r.json()["devices"]), (200, 1))
            post(SUB)                                                         # تکراری: رکورد دوم نمی‌سازه
            self.assertEqual(PushSubscription.objects.count(), 1)
            for i in range(12):
                post({"endpoint": f"https://push.example/{i}", "keys": SUB["keys"]})
            self.assertEqual(self.giver.push_subscriptions.count(), 10)      # سقف ۱۰ دستگاه

    def test_endpoint_moves_to_new_user_on_same_device(self):
        with override_settings(**VAPID):
            self.client.login(username="giver", password="x12345678")
            self.client.post(reverse("notifications:push_subscribe"), data=json.dumps(SUB), content_type="application/json")
            self.client.login(username="taker", password="x12345678")
            self.client.post(reverse("notifications:push_subscribe"), data=json.dumps(SUB), content_type="application/json")
        self.assertEqual(PushSubscription.objects.get().user, self.taker)

    def test_unsubscribe_only_own(self):
        self.subscribe(self.giver)
        self.client.login(username="taker", password="x12345678")
        self.client.post(reverse("notifications:push_unsubscribe"), data=json.dumps({"endpoint": SUB["endpoint"]}), content_type="application/json")
        self.assertEqual(PushSubscription.objects.count(), 1)                # مال کس دیگه‌ست
        self.client.login(username="giver", password="x12345678")
        self.client.post(reverse("notifications:push_unsubscribe"), data=json.dumps({"endpoint": SUB["endpoint"]}), content_type="application/json")
        self.assertEqual(PushSubscription.objects.count(), 0)

    @override_settings(**VAPID)
    def test_notify_sends_push_after_commit_and_payload(self):
        self.subscribe(self.giver)
        with mock.patch("pywebpush.webpush") as wp, self.captureOnCommitCallbacks(execute=True):
            notify(self.giver, "کسی کتابت رو خواست", "/exchanges/5/", kind="exchange")
        self.assertEqual(wp.call_count, 1)
        kw = wp.call_args.kwargs
        body = json.loads(kw["data"])
        self.assertEqual((body["title"], body["body"], body["url"]), ("مبادله‌ی کتاب", "کسی کتابت رو خواست", "/exchanges/5/"))
        self.assertEqual(kw["vapid_claims"], {"sub": "mailto:a@b.c"})
        self.assertEqual(kw["subscription_info"]["endpoint"], SUB["endpoint"])
        self.assertIsNotNone(PushSubscription.objects.get().last_used_at)

    @override_settings(**VAPID)
    def test_push_respects_preferences_and_users_without_subscription(self):
        self.subscribe(self.giver)
        NotificationPreference.objects.create(user=self.giver, push_chat=False)
        with mock.patch("pywebpush.webpush") as wp, self.captureOnCommitCallbacks(execute=True):
            notify(self.giver, "پیام", "/x/", kind="chat")                  # خاموش
            notify(self.taker, "بدون اشتراک", "/x/", kind="exchange")       # اشتراک نداره
            notify(self.giver, "نشان", "/x/", kind="badge")                 # push_other روشنه
        self.assertEqual(wp.call_count, 1)
        self.assertEqual(Notification.objects.filter(user=self.giver).count(), 2)  # اعلان داخلی همیشه ساخته می‌شه

    def test_not_configured_is_noop_but_in_site_notification_exists(self):
        self.subscribe(self.giver)
        with mock.patch("pywebpush.webpush") as wp, self.captureOnCommitCallbacks(execute=True):
            notify(self.giver, "سلام", "/", kind="exchange")
        wp.assert_not_called()
        self.assertEqual(Notification.objects.count(), 1)

    @override_settings(**VAPID)
    def test_dead_subscription_deleted_and_failures_counted(self):
        from pywebpush import WebPushException
        gone = self.subscribe(self.giver, "https://push.example/gone")
        flaky = self.subscribe(self.giver, "https://push.example/flaky")
        def fake(subscription_info, **kw):
            code = 410 if subscription_info["endpoint"].endswith("gone") else 500
            raise WebPushException("x", response=mock.Mock(status_code=code))
        with mock.patch("pywebpush.webpush", side_effect=fake):
            self.assertEqual(push_mod.send_payload(self.giver.pk, {"title": "t"}), 0)
        self.assertFalse(PushSubscription.objects.filter(pk=gone.pk).exists())
        flaky.refresh_from_db(); self.assertEqual(flaky.failures, 1)
        with mock.patch("pywebpush.webpush", side_effect=fake):
            for _ in range(4):
                push_mod.send_payload(self.giver.pk, {"title": "t"})
        self.assertFalse(PushSubscription.objects.filter(pk=flaky.pk).exists())  # بعد از ۵ خطای پیاپی

    @override_settings(**VAPID)
    def test_network_error_does_not_break_request(self):
        self.subscribe(self.giver)
        with mock.patch("pywebpush.webpush", side_effect=OSError("down")):
            self.assertEqual(push_mod.send_payload(self.giver.pk, {"title": "t"}), 0)
        self.assertEqual(PushSubscription.objects.count(), 1)

    @override_settings(**VAPID)
    def test_exchange_events_create_exchange_kind_and_chat_kind_notifications(self):
        self.subscribe(self.giver)
        with mock.patch("pywebpush.webpush") as wp, self.captureOnCommitCallbacks(execute=True):
            ex = services.request_book(self.book().pk, self.taker)
        self.assertEqual(Notification.objects.get(user=self.giver).kind, "exchange")
        self.assertEqual(wp.call_count, 1)
        services.accept(ex.pk, self.giver)
        self.client.login(username="taker", password="x12345678")
        self.client.post(reverse("exchanges:message", args=[ex.pk]), {"text": "سلام"})
        self.assertEqual(Notification.objects.filter(user=self.giver, kind="chat").count(), 1)

    def test_settings_page_prefs_and_test_endpoint(self):
        self.client.login(username="giver", password="x12345678")
        r = self.client.get(reverse("notifications:settings"))
        self.assertContains(r, "اعلان بیرون از سایت هنوز روی این سرور فعال نشده")
        with override_settings(**VAPID):
            r = self.client.get(reverse("notifications:settings"))
            self.assertContains(r, "data-push-root")
            self.assertContains(r, 'data-key="BPub"')
            self.client.post(reverse("notifications:settings"), {"push_exchange": "on"})
            prefs = NotificationPreference.objects.get(user=self.giver)
            self.assertEqual((prefs.push_exchange, prefs.push_chat, prefs.push_other), (True, False, False))
            self.subscribe(self.giver)
            with mock.patch("pywebpush.webpush") as wp:
                r = self.client.post(reverse("notifications:push_test"))
            self.assertEqual((r.json()["sent"], wp.call_count), (1, 1))

    def test_generate_vapid_keys_command(self):
        import base64
        from io import StringIO
        from django.core.management import call_command
        out = StringIO(); call_command("generate_vapid_keys", stdout=out)
        lines = dict(l.split("=", 1) for l in out.getvalue().strip().splitlines())
        pad = lambda s: s + "=" * (-len(s) % 4)
        self.assertEqual(len(base64.urlsafe_b64decode(pad(lines["VAPID_PUBLIC_KEY"]))), 65)   # نقطه‌ی فشرده‌نشده‌ی P-256
        self.assertEqual(len(base64.urlsafe_b64decode(pad(lines["VAPID_PRIVATE_KEY"]))), 32)
        # کلید ساخته‌شده واقعاً با pywebpush سازگاره
        from py_vapid import Vapid
        Vapid.from_raw(lines["VAPID_PRIVATE_KEY"].encode())


class PwaAssetTests(TestCase):
    def test_manifest_complete_and_files_exist_with_right_sizes(self):
        import json
        from pathlib import Path
        from PIL import Image
        root = Path(__file__).resolve().parent.parent
        m = json.loads((root / "static" / "manifest.json").read_text(encoding="utf-8"))
        for key in ("id", "name", "short_name", "start_url", "scope", "display", "icons", "shortcuts", "screenshots", "theme_color", "lang", "dir"):
            self.assertIn(key, m, key)
        self.assertEqual((m["lang"], m["dir"], m["display"]), ("fa", "rtl", "standalone"))
        self.assertTrue(any(i.get("purpose") == "maskable" for i in m["icons"]))
        for item in [*m["icons"], *m["screenshots"]]:
            path = root / item["src"].lstrip("/")
            self.assertTrue(path.exists(), item["src"])
            w, h = (int(x) for x in item["sizes"].split("x"))
            self.assertEqual(Image.open(path).size, (w, h), item["src"])
        self.assertGreaterEqual(len([s for s in m["screenshots"] if s["form_factor"] == "wide"]), 1)
        self.assertGreaterEqual(len([s for s in m["screenshots"] if s["form_factor"] == "narrow"]), 1)
        for sc in m["shortcuts"]:
            self.assertTrue(sc["url"].startswith("/"))

    def test_service_worker_versioned_and_has_push_handlers(self):
        r = self.client.get("/sw.js")
        body = r.content.decode()
        self.assertNotIn("__VERSION__", body)
        self.assertRegex(body, r'const VERSION = "[0-9a-f]+"')
        for needle in ("addEventListener(\"push\"", "notificationclick", "SKIP_WAITING", "/offline/"):
            self.assertIn(needle, body)
        self.assertEqual(r["Service-Worker-Allowed"], "/")
        self.assertIn("no-cache", r["Cache-Control"])

    def test_pages_link_manifest_icons_and_theme_colors(self):
        html = self.client.get("/").content.decode()
        for needle in ('rel="manifest"', "apple-touch-icon", 'name="theme-color"', "pwa.js", "viewport-fit=cover"):
            self.assertIn(needle, html)


class RichTextTests(TestCase):
    def render(self, text):
        from common.richtext import render
        return str(render(text))

    def test_html_is_escaped_everywhere(self):
        for payload in ("<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "**<b>x</b>**", "> <iframe src=//evil>", "- <a href=x>l</a>", "## <h1>x</h1>"):
            out = self.render(payload)
            self.assertNotIn("<script", out); self.assertNotIn("<img", out); self.assertNotIn("<iframe", out); self.assertNotIn("<a href=x", out); self.assertNotIn("<h1", out)

    def test_only_http_links_with_safe_rel(self):
        out = self.render("[بد](javascript:alert(1)) [دیتا](data:text/html,x) [خوب](https://example.com/a?b=1&c=2)")
        self.assertNotIn('href="javascript', out); self.assertNotIn('href="data', out)
        self.assertIn('href="https://example.com/a?b=1&amp;c=2"', out)
        self.assertIn('rel="nofollow ugc noopener noreferrer"', out)
        self.assertIn('target="_blank"', out)

    def test_attribute_breakout_blocked(self):
        out = self.render('[x](https://a.com" onclick="alert(1))')
        self.assertNotIn("onclick=", out.replace("&quot;", "")[:0] or out.split("<a")[1] if "<a" in out else "")
        self.assertNotIn("<a", out)

    def test_formatting_blocks(self):
        out = self.render("## تیتر\n\nمتن **پررنگ** و *مورب* و ***هر دو***\nخط دوم\n\n> نقل\n> ادامه\n\n- یک\n- دو\n\n۱. اول\n۲. دوم")
        for needle in ("<h3>تیتر</h3>", "<strong>پررنگ</strong>", "<em>مورب</em>", "<strong><em>هر دو</em></strong>", "<br>خط دوم", "<blockquote>نقل<br>ادامه</blockquote>",
                       "<ul><li>یک</li><li>دو</li></ul>", "<ol><li>اول</li><li>دوم</li></ol>"):
            self.assertIn(needle, out)

    def test_plain_helpers_and_limits(self):
        from common.richtext import count_links, plain, MAX_LEN
        self.assertEqual(count_links("[a](https://x.com) [b](http://y.com) [c](ftp://z)"), 2)
        self.assertEqual(plain("**سلام** [دنیا](https://x.com) ## تیتر"), "سلام دنیا تیتر")
        self.assertLessEqual(len(self.render("ا" * (MAX_LEN * 2))), MAX_LEN + 20)
        self.assertEqual(self.render(""), "")

    def test_template_filter(self):
        from django.template import Context, Template
        out = Template("{{ t|richtext }}").render(Context({"t": "<b>x</b>"}))
        self.assertIn("&lt;b&gt;", out)


class JalaliWidgetTests(TestCase):
    def field(self, **kw):
        from common.widgets import JalaliDateTimeField
        return JalaliDateTimeField(**kw)

    def test_conversion_to_tehran_aware_datetime(self):
        f = self.field()
        dt = f.clean(["1405", "1", "1", "09:30"])
        self.assertTrue(timezone.is_aware(dt))
        local = timezone.localtime(dt)
        self.assertEqual((local.year, local.month, local.day, local.hour, local.minute), (2026, 3, 21, 9, 30))

    def test_leap_and_invalid_dates(self):
        from django.core.exceptions import ValidationError
        f = self.field()
        self.assertIsNotNone(f.clean(["1403", "12", "30", ""]))           # ۱۴۰۳ کبیسه است
        for bad in (["1404", "12", "30", ""], ["1405", "7", "31", ""], ["1405", "13", "1", ""], ["1405", "1", "1", "ab:cd"]):
            with self.assertRaises(ValidationError):
                f.clean(bad)

    def test_required_optional_and_partial(self):
        from django.core.exceptions import ValidationError
        self.assertIsNone(self.field(required=False).clean(["", "", "", ""]))
        with self.assertRaises(ValidationError):
            self.field(required=True).clean(["", "", "", ""])
        with self.assertRaises(ValidationError):
            self.field(required=False).clean(["1405", "", "5", ""])      # ناقص

    def test_widget_roundtrip_and_render(self):
        from common.widgets import JalaliDateTimeWidget
        w = JalaliDateTimeWidget()
        dt = timezone.make_aware(__import__("datetime").datetime(2026, 10, 12, 18, 45), timezone.get_current_timezone())
        self.assertEqual(w.decompress(dt), ["1405", "7", "20", "18:45"])
        html = w.render("d", dt)
        self.assertIn('class="jdt"', html); self.assertIn("مهر", html); self.assertIn('type="time"', html)
        self.assertEqual(w.decompress(None), ["", "", "", ""])


class PostTests(Base):
    BODY = "این کتاب یکی از بهترین‌هاییه که تو سال‌های اخیر خوندم و فکر می‌کنم هر کتاب‌خوانی باید حداقل یک‌بار تجربه‌اش کنه. " * 3

    def post_data(self, **kw):
        d = {"title": "معرفی بوف کور", "book_title": "بوف کور", "book_author": "هدایت", "body": self.BODY, "rating": "5", "tags_text": "رمان، کلاسیک"}
        d.update(kw)
        return d

    def login(self, who="taker"):
        self.client.login(username=who, password="x12345678")

    def make(self, author=None, **kw):
        from posts.models import Post
        d = dict(author=author or self.taker, title="عنوان", book_title="کتاب", book_author="ن", body=self.BODY, status="published", published_at=timezone.now())
        d.update(kw)
        return Post.objects.create(**d)

    def test_first_post_goes_to_pending_then_trusted_auto_publishes(self):
        from posts.models import Post
        self.login()
        r = self.client.post(reverse("posts:create"), self.post_data(title="یک"))
        self.assertRedirects(r, reverse("posts:mine"))
        p1 = Post.objects.get(title="یک"); self.assertEqual(p1.status, "pending")
        self.assertEqual(self.client.get(reverse("posts:list")).context["page"].paginator.count, 0)   # هنوز عمومی نیست
        self.assertEqual(self.client.get(p1.get_absolute_url()).status_code, 200)                      # نویسنده می‌بینه
        self.client.logout()
        self.assertEqual(self.client.get(p1.get_absolute_url()).status_code, 404)                      # بقیه نه
        for t in ("دو", "سه"):                                                                         # دو نوشته‌ی تأییدشده ← اعتماد
            self.make(title=t)
        Post.objects.exclude(title="یک").update(created_at=timezone.now() - timedelta(days=2))         # از سقف روزانه خارج
        self.login()
        r = self.client.post(reverse("posts:create"), self.post_data(title="چهار"))
        self.assertEqual(Post.objects.get(title="چهار").status, "published")
        self.assertRedirects(r, Post.objects.get(title="چهار").get_absolute_url())

    def test_validation_rules(self):
        from posts.forms import PostForm
        f = lambda **kw: PostForm(self.post_data(**kw), user=self.taker)
        self.assertFalse(f(body="کوتاه").is_valid())
        self.assertIn("title", f(title="ببین http://spam.ir").errors)
        self.assertFalse(f(book_title="", book_author="").is_valid())                    # کتاب مشخص نیست
        links = " ".join(f"[l{i}](https://x{i}.com)" for i in range(5))
        self.assertIn("body", f(body=self.BODY + links).errors)                          # سقف لینک نویسنده‌ی تازه
        self.assertTrue(f().is_valid(), f().errors)

    def test_book_choice_limited_to_users_books_and_overrides_free_text(self):
        from posts.forms import PostForm, books_of
        mine = self.book(owner=self.taker, title="مال من")
        other = self.book(title="مال دیگری")
        self.assertEqual(list(books_of(self.taker)), [mine])
        f = PostForm(self.post_data(book=other.pk), user=self.taker)
        self.assertIn("book", f.errors)                                                   # کتاب غیرمرتبط
        f = PostForm(self.post_data(book=mine.pk), user=self.taker)
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual((f.cleaned_data["book_title"], f.cleaned_data["book_author"]), ("", ""))

    def test_received_book_counts_for_writing(self):
        from posts.forms import books_of
        ex = self.complete()
        self.assertIn(ex.book, books_of(self.taker))                                      # گیرنده
        self.assertIn(ex.book, books_of(self.giver))                                      # دهنده (مبادله‌ی کامل)

    def test_duplicate_title_and_daily_limit(self):
        self.login()
        self.client.post(reverse("posts:create"), self.post_data(title="تکراری"))
        r = self.client.post(reverse("posts:create"), self.post_data(title="تکراری"))
        self.assertEqual(r.status_code, 200)                                              # عنوان تازه ثبت‌شده
        for i in range(2):
            self.client.post(reverse("posts:create"), self.post_data(title=f"روز {i}"))
        from posts.models import Post
        self.assertEqual(Post.objects.filter(author=self.taker).count(), 3)
        r = self.client.post(reverse("posts:create"), self.post_data(title="چهارمی"))
        self.assertRedirects(r, reverse("posts:mine"))
        self.assertEqual(Post.objects.filter(author=self.taker).count(), 3)               # سقف ۳ در روز

    def test_tags_normalized_and_capped(self):
        p = self.make()
        p.set_tags_from_text("رمان، ك‌لاسیک,رمان , c , d, e, f, g")
        self.assertEqual(p.tags.count(), 5)
        p.set_tags_from_text("كتاب, کتاب")                                               # ک عربی = ک فارسی
        self.assertEqual(p.tags.count(), 1)

    def test_list_filters_search_sort_and_detail_view_count(self):
        a = self.make(title="جنگ و صلح", book_title="جنگ و صلح", book_author="تولستوی")
        b = self.make(title="سووشون", book_title="سووشون", book_author="دانشور", view_count=50, is_featured=False)
        self.make(title="پیش‌نویس", status="draft", published_at=None)
        get = lambda **q: [p.title for p in self.client.get(reverse("posts:list"), q).context["page"]]
        self.assertEqual(sorted(get()), ["جنگ و صلح", "سووشون"])
        self.assertEqual(get(q="دانشور"), ["سووشون"])
        self.assertEqual(get(q="سوشون".replace("و", "و")), [])                           # نرمال‌سازی ولی غلط املایی نه
        self.assertEqual(get(sort="popular")[0], "سووشون")
        a.set_tags_from_text("تاریخی")
        self.assertEqual(get(tag=a.tags.first().pk), ["جنگ و صلح"])
        self.client.get(a.get_absolute_url())
        a.refresh_from_db(); self.assertEqual(a.view_count, 0)                           # شمارش فقط با بیکن جاوااسکریپت (analytics)
        self.assertEqual(b.get_absolute_url(), reverse("posts:detail", args=[b.slug]))

    def test_detail_seo_jsonld_and_review_type(self):
        import json, re
        p = self.make(title="بررسی", rating=4)
        html = self.client.get(p.get_absolute_url()).content.decode()
        ld = json.loads(re.search(r'application/ld\+json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual((ld["@type"], ld["reviewRating"]["ratingValue"]), ("Review", 4))
        self.assertIn('property="og:type" content="article"', html)
        self.assertNotIn("noindex", html)
        draft = self.make(title="خصوصی", status="pending")
        self.login()
        self.assertIn("noindex", self.client.get(draft.get_absolute_url()).content.decode())

    def test_body_renders_safely_on_page(self):
        p = self.make(body="<script>alert(1)</script> **پررنگ** " + self.BODY)
        html = self.client.get(p.get_absolute_url()).content.decode()
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("<strong>پررنگ</strong>", html)

    def test_edit_permissions_and_requeue_for_untrusted(self):
        from posts.models import Post
        p = self.make(status="published")
        self.login("giver")
        self.assertEqual(self.client.get(reverse("posts:edit", args=[p.slug])).status_code, 404)    # مال دیگری
        self.assertEqual(self.client.post(reverse("posts:delete", args=[p.slug])).status_code, 404)
        self.login()
        self.client.post(reverse("posts:edit", args=[p.slug]), self.post_data(title="ویرایش‌شده"))
        p.refresh_from_db()
        self.assertEqual((p.title, p.status), ("ویرایش‌شده", "pending"))                          # فقط ۱ نوشته‌ی تأییدشده بود ← دوباره صف
        self.client.post(reverse("posts:delete", args=[p.slug]))
        self.assertFalse(Post.objects.filter(pk=p.pk).exists())

    def test_admin_moderation_notifies_and_awards_badge(self):
        p = self.make(status="pending", published_at=None)
        boss = User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        self.client.post("/admin/posts/post/", {"action": "approve", "_selected_action": [p.pk]})
        p.refresh_from_db()
        self.assertEqual(p.status, "published"); self.assertIsNotNone(p.published_at)
        self.assertTrue(Notification.objects.filter(user=self.taker, text__contains="منتشر شد", kind="event").exists())
        self.assertTrue(self.taker.user_badges.filter(badge__code="writer").exists())
        q = self.make(status="pending", published_at=None, title="رد می‌شه")
        self.client.post("/admin/posts/post/", {"action": "reject_generic", "_selected_action": [q.pk]})
        q.refresh_from_db(); self.assertEqual(q.status, "rejected"); self.assertTrue(q.reject_reason)
        self.assertEqual(boss.is_staff, True)

    def test_staff_posts_publish_immediately_and_preview_endpoint(self):
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        self.client.post(reverse("posts:create"), self.post_data(title="رسمی"))
        from posts.models import Post
        self.assertEqual(Post.objects.get(title="رسمی").status, "published")
        r = self.client.post(reverse("posts:preview"), {"body": "**x** <script>"})
        self.assertIn("<strong>x</strong>", r.json()["html"]); self.assertNotIn("<script>", r.json()["html"])
        self.client.logout()
        self.assertEqual(self.client.post(reverse("posts:preview"), {"body": "x"}).status_code, 302)

    def test_report_post_and_book_page_section_and_author_page(self):
        from trust.models import Report
        p = self.make(author=self.giver)
        self.login()
        url = reverse("trust:report", args=["post", p.pk])
        self.client.post(url, {"reason": "other", "description": "x"}); self.client.post(url, {"reason": "other"})
        self.assertEqual(Report.objects.get().accused, self.giver)
        self.assertEqual(Report.objects.get().target_label, "معرفی «عنوان»")
        self.login("giver")
        self.client.post(url, {"reason": "other"})                                         # گزارش خودش نه
        self.assertEqual(Report.objects.count(), 1)
        book = self.book(); Post = type(p); Post.objects.filter(pk=p.pk).update(book=book)
        html = self.client.get(reverse("books:detail", args=[book.pk])).content.decode()
        self.assertIn("معرفی‌ها", html); self.assertIn(p.title, html)
        self.assertEqual(len(self.client.get(reverse("posts:author", args=["giver"])).context["page"]), 1)

    def test_badges_and_post_challenge(self):
        from challenges.models import Challenge
        c = Challenge.objects.create(title="یه معرفی", kind="post", target=2, starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() + timedelta(days=9))
        for i in range(2):
            self.make(title=f"p{i}")
        self.assertEqual(c.progress(self.taker), 2)
        from accounts.badges import check_badges
        check_badges(self.taker)
        codes = set(self.taker.user_badges.values_list("badge__code", flat=True))
        self.assertIn("writer", codes); self.assertIn(c.badge_code, codes); self.assertNotIn("columnist", codes)
        for i in range(3):
            self.make(title=f"q{i}")
        check_badges(self.taker)
        self.assertTrue(self.taker.user_badges.filter(badge__code="columnist").exists())

    def test_reserved_slug_and_unique_slugs(self):
        a = self.make(title="new"); b = self.make(title="new")
        self.assertEqual(a.slug, "new-post"); self.assertEqual(b.slug, "new-post-2")
        self.assertEqual(self.client.get(a.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get("/posts/new/").status_code, 302)                  # مسیر ثابت (لاگین)


class AnnouncementTests(Base):
    def make(self, **kw):
        from announcements.models import Announcement
        d = dict(title="نمایشگاه کتاب", kind="book_fair", summary="خلاصه", status="published", published_at=timezone.now(),
                 starts_at=timezone.now() + timedelta(days=3), city=self.tehran, venue="مصلی", submitted_by=self.giver)
        d.update(kw)
        return Announcement.objects.create(**d)

    def form_data(self, **kw):
        d = {"title": "رونمایی کتاب تازه", "kind": "launch", "summary": "رونمایی با حضور نویسنده", "city": self.tehran.pk,
             "starts_at_0": "1405", "starts_at_1": "9", "starts_at_2": "10", "starts_at_3": "17:30", "venue": "کتابخانه‌ی ملی", "is_free": "on"}
        d.update(kw)
        return d

    def test_upcoming_past_tabs_and_ordering(self):
        soon = self.make(title="زودتر", starts_at=timezone.now() + timedelta(days=1))
        later = self.make(title="دیرتر", starts_at=timezone.now() + timedelta(days=9))
        feat = self.make(title="ویژه", starts_at=timezone.now() + timedelta(days=20), is_featured=True)
        old = self.make(title="قدیمی", starts_at=timezone.now() - timedelta(days=5), ends_at=timezone.now() - timedelta(days=4))
        ongoing = self.make(title="در جریان", starts_at=timezone.now() - timedelta(days=1), ends_at=timezone.now() + timedelta(days=2))
        news = self.make(title="خبر تازه", kind="news", starts_at=None, venue="", city=None)
        self.make(title="پیش‌نویس", status="pending")
        titles = lambda **q: [a.title for a in self.client.get(reverse("announcements.list".replace(".", ":")), q).context["page"]]
        up = titles()
        self.assertEqual(up[0], "ویژه")                                                     # ویژه اول
        self.assertEqual(set(up), {"ویژه", "زودتر", "دیرتر", "در جریان", "خبر تازه"})
        self.assertNotIn("قدیمی", up); self.assertNotIn("پیش‌نویس", up)
        self.assertEqual(titles(tab="past"), ["قدیمی"])
        self.assertTrue(old.is_past); self.assertFalse(ongoing.is_past); self.assertFalse(soon.is_past)
        self.assertTrue(news.is_news and later and feat)

    def test_filters_by_province_city_kind_online(self):
        self.make(title="تهران")
        self.make(title="اصفهان", city=self.isfahan)
        self.make(title="آنلاین", is_online=True, city=None, venue="")
        self.make(title="کارگاه", kind="workshop")
        names = lambda **q: sorted(a.title for a in self.client.get(reverse("announcements:list"), q).context["page"])
        self.assertEqual(names(province=self.isfahan.province_id), ["اصفهان"])
        self.assertEqual(names(city=self.tehran.pk), ["تهران", "کارگاه"])
        self.assertEqual(names(kind="workshop"), ["کارگاه"])
        self.assertEqual(names(online="on"), ["آنلاین"])
        self.assertEqual(names(province=self.tehran.province_id, city=self.isfahan.pk), ["تهران", "کارگاه"])   # شهر نامربوط نادیده

    def test_detail_jsonld_event_and_news_and_hidden_pending(self):
        import json, re
        a = self.make(is_free=False, price_note="۵۰ هزار تومان", organizer="نشر آگاه")
        html = self.client.get(a.get_absolute_url()).content.decode()
        ld = json.loads(re.search(r'application/ld\+json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual((ld["@type"], ld["isAccessibleForFree"], ld["location"]["@type"]), ("Event", False, "Place"))
        self.assertIn("افزودن به تقویم", html); self.assertIn("۵۰ هزار تومان", html)
        on = self.make(title="وبینار", is_online=True, city=None, venue="", link="https://meet.example/x")
        ld = json.loads(re.search(r'application/ld\+json">(.*?)</script>', self.client.get(on.get_absolute_url()).content.decode(), re.S).group(1))
        self.assertEqual(ld["location"]["@type"], "VirtualLocation")
        n = self.make(kind="news", starts_at=None, venue="", city=None)
        ld = json.loads(re.search(r'application/ld\+json">(.*?)</script>', self.client.get(n.get_absolute_url()).content.decode(), re.S).group(1))
        self.assertEqual(ld["@type"], "NewsArticle")
        hidden = self.make(status="pending")
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 404)
        self.client.login(username="giver", password="x12345678")                           # ثبت‌کننده
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 200)
        self.assertEqual(self.client.get(reverse("announcements:detail_pk", args=[a.pk])).status_code, 200)

    def test_ics_valid_and_escaped_and_folded(self):
        a = self.make(title="رونمایی; «کتاب» تازه, ویژه", summary="خط اول\nخط دوم", address="خیابان, پلاک ۵" + " طولانی" * 30)
        r = self.client.get(reverse("announcements:ics", args=[a.pk]))
        self.assertEqual(r["Content-Type"], "text/calendar; charset=utf-8")
        body = r.content.decode()
        self.assertTrue(body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n"))
        for needle in ("BEGIN:VEVENT", f"UID:announcement-{a.pk}@hamvaraq", "DTSTART:", "DTEND:", "\;", "\\,", "\\n"):
            self.assertIn(needle, body)
        for line in body.split("\r\n"):
            self.assertLessEqual(len(line.encode()), 76, line)                              # شکستن خطوط بلند (RFC 5545)
        news = self.make(kind="news", starts_at=None)
        self.assertEqual(self.client.get(reverse("announcements:ics", args=[news.pk])).status_code, 404)

    def test_submit_form_jalali_pending_and_validation(self):
        from announcements.models import Announcement
        self.client.login(username="taker", password="x12345678")
        r = self.client.post(reverse("announcements:create"), self.form_data())
        self.assertRedirects(r, reverse("announcements:mine"))
        a = Announcement.objects.get()
        self.assertEqual((a.status, a.submitted_by), ("pending", self.taker))
        local = timezone.localtime(a.starts_at)
        self.assertEqual((local.year, local.month, local.day, local.hour, local.minute), (2026, 12, 1, 17, 30))   # ۱۰ آذر ۱۴۰۵
        bad = lambda **kw: self.client.post(reverse("announcements:create"), self.form_data(**kw)).status_code
        self.assertEqual(bad(starts_at_0="", starts_at_1="", starts_at_2=""), 200)          # رویداد بدون تاریخ
        self.assertEqual(bad(ends_at_0="1405", ends_at_1="9", ends_at_2="9"), 200)          # پایان قبل از شروع
        self.assertEqual(bad(city="", venue=""), 200)                                       # بدون شهر/محل
        self.assertEqual(Announcement.objects.count(), 1)
        ok_news = self.client.post(reverse("announcements:create"), self.form_data(kind="news", starts_at_0="", starts_at_1="", starts_at_2="", city="", venue="", title="خبر"))
        self.assertEqual(ok_news.status_code, 302)

    def test_staff_publish_immediately_and_city_notification(self):
        from announcements.models import Announcement
        User.objects.create_superuser("boss", password="x12345678", city=self.tehran)
        local_user = User.objects.create_user("همشهری", password="x12345678", city=self.tehran)
        User.objects.create_user("دور", password="x12345678", city=self.isfahan)
        self.client.login(username="boss", password="x12345678")
        self.client.post(reverse("announcements:create"), self.form_data())
        a = Announcement.objects.get()
        self.assertEqual(a.status, "published")
        names = set(Notification.objects.filter(kind="event").values_list("user__username", flat=True))
        self.assertIn("همشهری", names); self.assertIn("giver", names) if self.giver.city_id == self.tehran.pk else None
        self.assertNotIn("دور", names); self.assertNotIn("boss", names)                     # شهر دیگه و ثبت‌کننده نه
        self.assertTrue(local_user.notifications.filter(text__contains="رونمایی").exists())

    def test_online_and_news_do_not_mass_notify(self):
        from announcements import services
        online = self.make(is_online=True, city=None)
        news = self.make(kind="news", starts_at=None)
        self.assertEqual((services.notify_city(online), services.notify_city(news)), (0, 0))

    def test_admin_moderation_flow(self):
        item = self.make(status="pending", published_at=None, submitted_by=self.taker)
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        self.client.post("/admin/announcements/announcement/", {"action": "approve", "_selected_action": [item.pk]})
        item.refresh_from_db(); self.assertEqual(item.status, "published")
        self.assertTrue(Notification.objects.filter(user=self.taker, text__contains="منتشر شد").exists())
        r = self.make(status="pending", title="تبلیغ", published_at=None, submitted_by=self.taker)
        self.client.post("/admin/announcements/announcement/", {"action": "reject_generic", "_selected_action": [r.pk]})
        r.refresh_from_db(); self.assertEqual(r.status, "rejected"); self.assertTrue(r.reject_reason)

    def test_edit_rules_and_daily_limit(self):
        from announcements.models import Announcement
        item = self.make(status="rejected", submitted_by=self.taker)
        pub = self.make(title="منتشر", submitted_by=self.taker)
        self.client.login(username="taker", password="x12345678")
        self.assertEqual(self.client.get(reverse("announcements:edit", args=[item.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("announcements:edit", args=[pub.pk])).status_code, 404)    # منتشرشده قابل ویرایش نیست
        self.client.login(username="giver", password="x12345678")
        self.assertEqual(self.client.get(reverse("announcements:edit", args=[item.pk])).status_code, 404)   # مال دیگری
        self.client.login(username="taker", password="x12345678")
        Announcement.objects.filter(submitted_by=self.taker).delete()
        for i in range(3):
            self.client.post(reverse("announcements:create"), self.form_data(title=f"اطلاعیه {i}"))
        r = self.client.post(reverse("announcements:create"), self.form_data(title="چهارمی"))
        self.assertRedirects(r, reverse("announcements:mine"))
        self.assertEqual(Announcement.objects.filter(submitted_by=self.taker).count(), 3)

    def test_bookmark_toggle_and_reminder_command_once(self):
        from io import StringIO
        from django.core.management import call_command
        from announcements.models import AnnouncementBookmark
        soon = self.make(title="فردا", starts_at=timezone.now() + timedelta(hours=20))
        far = self.make(title="دور", starts_at=timezone.now() + timedelta(days=10))
        self.client.login(username="taker", password="x12345678")
        for a in (soon, far):
            self.client.post(reverse("announcements:bookmark", args=[a.pk]))
        self.assertEqual(AnnouncementBookmark.objects.count(), 2)
        out = StringIO(); call_command("announcement_reminders", stdout=out)
        self.assertIn("1", out.getvalue())
        self.assertEqual(Notification.objects.filter(user=self.taker, text__contains="یادآوری").count(), 1)
        call_command("announcement_reminders", stdout=StringIO())                         # دوباره: تکراری نمی‌فرسته
        self.assertEqual(Notification.objects.filter(user=self.taker, text__contains="یادآوری").count(), 1)
        self.client.post(reverse("announcements:bookmark", args=[far.pk]))                  # برداشتن
        self.assertEqual(AnnouncementBookmark.objects.count(), 1)

    def test_report_announcement_and_admin_created_has_no_accused(self):
        from trust.models import Report
        from trust.services import apply_decision
        a = self.make(submitted_by=None)
        self.client.login(username="taker", password="x12345678")
        self.client.post(reverse("trust:report", args=["announcement", a.pk]), {"reason": "other"})
        r = Report.objects.get(); self.assertIsNone(r.accused)
        r.decision, r.decision_note = "ban", "x"
        apply_decision(r, self.giver)                                                      # کاربری برای مسدودسازی نیست؛ خطا نمی‌ده
        r.refresh_from_db(); self.assertEqual((r.status, r.decision), ("closed", "reject"))

    def test_home_and_landing_sections_and_sitemap(self):
        from posts.models import Post
        a = self.make()
        Post.objects.create(author=self.taker, title="معرفی‌ای", book_title="ک", book_author="ن", body="ب" * 200, status="published", published_at=timezone.now())
        html = self.client.get("/").content.decode()
        self.assertIn("اتفاق‌های فرهنگی", html); self.assertIn("معرفی‌های تازه", html); self.assertIn(a.title, html)
        sm = self.client.get("/sitemap.xml").content.decode()
        self.assertIn(f"/announcements/{a.pk}/", sm); self.assertIn("/posts/", sm)
        User.objects.filter(pk=self.giver.pk).update(city=self.tehran)
        self.client.login(username="giver", password="x12345678")
        r = self.client.get("/")
        self.assertEqual([e.title for e in r.context["events"]], [a.title])

    def test_staff_dashboard_queues(self):
        self.make(status="pending")
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        r = self.client.get("/panel/")
        self.assertEqual(r.context["d"]["queues"], {"posts": 0, "announcements": 1})
        self.assertContains(r, "اطلاعیه منتظر تأیید")
        self.assertEqual(self.client.get("/staff/").status_code, 302)  # آدرس قدیمی به پنل می‌ره


class SupportTests(Base):
    def post(self, **over):
        data = {"category": "bug", "subject": "دکمه کار نمی‌کنه", "message": "وقتی روی درخواست می‌زنم هیچ اتفاقی نمی‌افته.", "page_url": "/books/1/", "contact": "", "website": ""}
        data.update(over)
        return self.client.post(reverse("support:new"), data)

    def test_member_submits_and_sees_status_and_reply(self):
        from support.models import Ticket
        self.client.login(username="taker", password="x12345678")
        self.assertEqual(self.client.get(reverse("support:new")).status_code, 200)
        self.assertEqual(self.post().status_code, 302)
        t = Ticket.objects.get()
        self.assertEqual((t.user, t.status, t.page_url), (self.taker, "new", "/books/1/"))
        self.assertContains(self.client.get(reverse("support:mine")), "دکمه کار نمی‌کنه")
        boss = User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        r = self.client.post(reverse("panel:ticket", args=[t.pk]), {"status": "resolved", "reply": "درست شد."})
        self.assertEqual(r.status_code, 302)
        t.refresh_from_db()
        self.assertEqual((t.status, t.handled_by), ("resolved", boss))
        self.assertTrue(Notification.objects.filter(user=self.taker, kind="report", text__contains="پاسخ داد").exists())
        self.client.login(username="taker", password="x12345678")
        self.assertContains(self.client.get(t.get_absolute_url()), "درست شد.")

    def test_guest_can_report_with_contact_but_honeypot_and_short_text_fail(self):
        from support.models import Ticket
        self.assertEqual(self.post(contact="a@b.ir").status_code, 302)
        self.assertEqual(Ticket.objects.get().user, None)
        self.assertEqual(self.post(website="spam").status_code, 200)
        self.assertEqual(self.post(message="کوتاه").status_code, 200)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_only_owner_sees_ticket_and_outside_page_url_dropped(self):
        from support.models import Ticket
        self.client.login(username="taker", password="x12345678")
        self.post(page_url="https://evil.example/x")
        t = Ticket.objects.get()
        self.assertEqual(t.page_url, "")
        self.client.login(username="giver", password="x12345678")
        self.assertEqual(self.client.get(t.get_absolute_url()).status_code, 404)

    def test_rate_limited(self):
        self.client.login(username="taker", password="x12345678")
        for _ in range(5):
            self.post()
        self.assertEqual(self.post().status_code, 429)


class PanelTests(Base):
    def setUp(self):
        super().setUp()
        self.boss = User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")

    def test_panel_is_staff_only(self):
        self.client.logout()
        self.assertEqual(self.client.get("/panel/").status_code, 302)
        self.client.login(username="taker", password="x12345678")
        for url in ("/panel/", "/panel/users/", "/panel/posts/", "/panel/settings/", "/panel/audit/"):
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.assertEqual(self.client.post(f"/panel/users/{self.giver.pk}/action/", {"do": "ban", "note": "x"}).status_code, 302)
        self.giver.refresh_from_db()
        self.assertEqual(self.giver.status, "active")

    def test_all_sections_render(self):
        from support.models import Ticket
        Ticket.objects.create(user=self.taker, subject="س", message="پیام کافی برای تست")
        for url in ("/panel/", "/panel/reports/", "/panel/tickets/", "/panel/exchanges/", "/panel/exchanges/?disputed=1", "/panel/users/", f"/panel/users/{self.taker.pk}/",
                    "/panel/users/?f=banned&q=ta", "/panel/books/", "/panel/books/?status=available&q=x", "/panel/posts/", "/panel/announcements/", "/panel/challenges/",
                    "/panel/challenges/new/", "/panel/settings/", "/panel/audit/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_user_actions_and_guards(self):
        url = reverse("panel:user_action", args=[self.taker.pk])
        self.client.post(url, {"do": "warn", "note": "اخطار تست"})
        self.client.post(url, {"do": "points", "delta": "3", "note": "جبران"})
        self.taker.refresh_from_db()
        self.assertEqual((self.taker.warnings, self.taker.points), (1, 4))
        self.client.post(url, {"do": "restrict", "note": "بدقولی"})
        self.taker.refresh_from_db()
        self.assertTrue(self.taker.is_restricted)
        self.client.post(url, {"do": "lift"})
        self.client.post(url, {"do": "ban", "note": "تخلف"})
        self.taker.refresh_from_db()
        self.assertEqual((self.taker.status, self.taker.is_active), ("banned", False))
        self.client.post(url, {"do": "lift"})
        self.taker.refresh_from_db()
        self.assertEqual((self.taker.status, self.taker.is_active), ("active", True))
        self.assertEqual(self.client.post(url, {"do": "ban", "note": ""}).status_code, 302)   # بدون دلیل اعمال نمی‌شه
        self.taker.refresh_from_db()
        self.assertEqual(self.taker.status, "active")
        self.assertGreaterEqual(AuditLog.objects.filter(target="کاربر taker").count(), 5)
        # خودش و مدیر دیگه محافظت دارن
        self.client.post(reverse("panel:user_action", args=[self.boss.pk]), {"do": "ban", "note": "x"})
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_active)
        staff = User.objects.create_user("stf", password="x12345678", is_staff=True)
        self.client.login(username="stf", password="x12345678")
        self.client.post(reverse("panel:user_action", args=[self.boss.pk]), {"do": "ban", "note": "x"})
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_active)
        self.assertEqual(staff.pk, User.objects.get(username="stf").pk)

    def test_post_and_announcement_moderation(self):
        from announcements.models import Announcement
        from posts.models import Post
        post = Post.objects.create(author=self.taker, title="معرفی", body="متن " * 60, status="pending")
        self.client.post(reverse("panel:post_action", args=[post.pk]), {"do": "reject", "note": ""})
        post.refresh_from_db()
        self.assertEqual(post.status, "pending")                          # رد بدون دلیل نمی‌شه
        self.client.post(reverse("panel:post_action", args=[post.pk]), {"do": "reject", "note": "کوتاه"})
        post.refresh_from_db()
        self.assertEqual((post.status, post.reject_reason), ("rejected", "کوتاه"))
        self.client.post(reverse("panel:post_action", args=[post.pk]), {"do": "approve"})
        self.client.post(reverse("panel:post_action", args=[post.pk]), {"do": "feature"})
        post.refresh_from_db()
        self.assertEqual((post.status, post.is_featured), ("published", True))
        a = Announcement.objects.create(title="رویداد", kind="other", summary="خ", submitted_by=self.taker, status="pending")
        self.client.post(reverse("panel:announcement_action", args=[a.pk]), {"do": "approve"})
        a.refresh_from_db()
        self.assertEqual(a.status, "published")
        self.client.post(reverse("panel:announcement_action", args=[a.pk]), {"do": "delete"})
        self.assertFalse(Announcement.objects.exists())

    def test_report_decision_and_challenge_crud(self):
        from challenges.models import Challenge
        from trust.models import Report
        r = Report.objects.create(reporter=self.giver, target_user=self.taker, reason="abuse", description="توهین")
        self.client.post(reverse("panel:report", args=[r.pk]), {"decision": "warn", "decision_note": ""})
        r.refresh_from_db()
        self.assertEqual(r.status, "open")                                # بدون دلیل بسته نمی‌شه
        self.client.post(reverse("panel:report", args=[r.pk]), {"decision": "warn", "decision_note": "رعایت کن"})
        r.refresh_from_db(); self.taker.refresh_from_db()
        self.assertEqual((r.status, r.handled_by, self.taker.warnings), ("closed", self.boss, 1))
        data = {"title": "چالش تازه", "description": "", "kind": "give", "target": 2, "is_active": "on",
                "starts_at_0": "1405", "starts_at_1": "7", "starts_at_2": "1", "starts_at_3": "10:00",
                "ends_at_0": "1405", "ends_at_1": "8", "ends_at_2": "1", "ends_at_3": "10:00"}
        resp = self.client.post(reverse("panel:challenge_new"), data)
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["form"].errors)
        c = Challenge.objects.get(title="چالش تازه")
        self.client.post(reverse("panel:challenge_action", args=[c.pk]))
        c.refresh_from_db()
        self.assertFalse(c.is_active)
        self.client.post(reverse("panel:challenge_action", args=[c.pk]), {"do": "delete"})
        self.assertFalse(Challenge.objects.filter(title="چالش تازه").exists())

    def test_book_delete_guard_and_settings(self):
        book = self.book(title="حذفی")
        ex = services.request_book(book.pk, self.taker)
        self.client.post(reverse("panel:book_delete", args=[book.pk]), {"note": "x"})
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())          # مبادله‌ی در جریان دارد
        services.reject(ex.pk, self.giver)
        self.client.post(reverse("panel:book_delete", args=[book.pk]), {"note": "نامناسب"})
        self.assertFalse(Book.objects.filter(pk=book.pk).exists())
        from common.models import SiteSetting
        self.addCleanup(lambda: setattr(SiteSetting, "_cache", None))
        data = {f: getattr(SiteSetting.load(), f) for f in ("tagline", "hero_title", "hero_subtitle", "cta_title", "cta_text", "footer_text")}
        data["tagline"] = "شعار پنل"
        self.client.post(reverse("panel:settings"), data)
        self.assertEqual(SiteSetting.load().tagline, "شعار پنل")

    def test_staff_sees_todo_badge_and_next_redirect_is_safe(self):
        from support.models import Ticket
        Ticket.objects.create(subject="س", message="پیام کافی برای تست")
        self.assertContains(self.client.get("/"), "پنل مدیریت")
        r = self.client.post(reverse("panel:report_reviewing", args=[1]), {"next": "https://evil.example/"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("panel:reports"))


BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class AnalyticsTests(Base):
    def setUp(self):
        super().setUp()
        self.b = self.book(title="بوف کور")
        self.hit_url = reverse("analytics:hit")

    def token(self, url, client=None, ua=BROWSER, ip="1.2.3.4"):
        import re
        r = (client or self.client).get(url, HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)
        m = re.search(r'name="hv-view" content="([^"]+)"', r.content.decode())
        return m.group(1) if m else ""

    def hit(self, token, client=None, ua=BROWSER, ip="1.2.3.4", wait=10):
        import time
        from unittest import mock
        with mock.patch("analytics.tracking.time.time", return_value=time.time() + wait):
            return (client or self.client).post(self.hit_url, {"t": token}, HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)

    def test_unique_view_counts_once_per_visitor_even_with_repeats(self):
        from analytics.models import DailyVisitor, ViewLog
        t = self.token(self.b.get_absolute_url())
        self.assertEqual(self.hit(t).status_code, 204)
        self.hit(self.token(self.b.get_absolute_url())); self.hit(t)
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 1)
        self.assertEqual((ViewLog.objects.count(), DailyVisitor.objects.count()), (1, 1))
        # بازدیدکننده‌ی دیگه (آی‌پی دیگه) جداگانه شمرده می‌شه
        from django.test import Client
        self.hit(self.token(self.b.get_absolute_url(), Client(), ip="9.9.9.9"), Client(), ip="9.9.9.9")
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 2)

    def test_cookie_reset_does_not_create_new_unique(self):
        from django.test import Client
        self.hit(self.token(self.b.get_absolute_url()))
        fresh = Client()                                    # بدون کوکی ولی همون آی‌پی و مرورگر
        self.hit(self.token(self.b.get_absolute_url(), fresh), fresh)
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 1)

    def test_bots_staff_owner_and_fast_or_forged_hits_are_ignored(self):
        url = self.b.get_absolute_url()
        self.assertEqual(self.token(url, ua="Googlebot/2.1 (+http://www.google.com/bot.html)"), "")
        self.assertEqual(self.token(url, ua="curl/8.0"), "")
        self.assertEqual(self.token(url, ua=""), "")
        t = self.token(url)
        self.hit(t, wait=1)                                  # خیلی زود برگشته
        self.hit("forged.token")
        self.hit(t, ua="python-requests/2.0")
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 0)
        self.client.login(username="giver", password="x12345678")    # صاحب کتاب: فقط حضور در سایت
        owner_t = self.token(url)
        self.hit(owner_t)
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 0)
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        self.assertEqual(self.token(url), "")
        self.assertEqual(self.token("/panel/"), "")

    def test_member_view_counts_and_old_token_expires(self):
        import time
        from unittest import mock
        self.client.login(username="taker", password="x12345678")
        t = self.token(self.b.get_absolute_url())
        with mock.patch("analytics.tracking.time.time", return_value=time.time() + 7200):
            self.client.post(self.hit_url, {"t": t}, HTTP_USER_AGENT=BROWSER)
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 0)               # توکن بیش از یک ساعت قدیمیه
        self.hit(t)
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 1)
        from analytics.models import ViewLog
        self.assertTrue(ViewLog.objects.get().is_member)

    def test_posts_events_and_site_visits(self):
        from announcements.models import Announcement
        from posts.models import Post
        post = Post.objects.create(author=self.giver, title="معرفی", body="متن " * 60, status="published", published_at=timezone.now())
        ev = Announcement.objects.create(title="رویداد", kind="other", summary="خ", status="published", submitted_by=self.giver, published_at=timezone.now())
        self.hit(self.token(post.get_absolute_url())); self.hit(self.token(ev.get_absolute_url()))
        self.hit(self.token("/"), ip="5.5.5.5")
        post.refresh_from_db(); ev.refresh_from_db()
        self.assertEqual((post.view_count, ev.view_count), (1, 1))
        from analytics.models import DailyVisitor
        self.assertEqual(DailyVisitor.objects.count(), 2)    # ۲ بازدیدکننده‌ی متفاوت (آی‌پی ۱.۲.۳.۴ و ۵.۵.۵.۵)

    def test_unknown_object_and_get_not_allowed(self):
        import time
        from unittest import mock
        from django.core import signing
        bad = signing.dumps({"k": "book", "i": 99999, "o": 0, "t": int(time.time())}, salt="hv-view")
        self.hit(bad)
        from analytics.models import ViewLog
        self.assertEqual(ViewLog.objects.count(), 0)
        self.assertEqual(self.client.get(self.hit_url).status_code, 405)
        with mock.patch("analytics.tracking.hit", return_value=False):
            self.hit(self.token(self.b.get_absolute_url()))
        self.b.refresh_from_db()
        self.assertEqual(self.b.view_count, 0)               # سقف نرخ

    def test_panel_stats_and_my_stats_pages(self):
        from analytics.services import admin_stats, user_stats
        services.request_book(self.b.pk, self.taker)
        self.hit(self.token(self.b.get_absolute_url()))
        s = admin_stats(30)
        self.assertEqual((s["views"]["by_kind"].get("book"), s["requests"]["total"], s["site"]["unique"]), (1, 1, 1))
        self.assertEqual(s["views"]["top_books"][0][0], self.b)
        self.assertEqual(s["requests"]["conversion"], 100)
        u = user_stats(self.giver)["tiles"]
        self.assertEqual((u["book_views"], u["requests"]), (1, 1))
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        for days in ("7", "30", "90", "x"):
            self.assertEqual(self.client.get("/panel/stats/", {"days": days}).status_code, 200)
        self.client.login(username="giver", password="x12345678")
        r = self.client.get(reverse("accounts:stats"))
        self.assertContains(r, "بوف کور")
        self.assertContains(self.client.get(self.b.get_absolute_url()), "بازدید یکتا")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:stats")).status_code, 302)
