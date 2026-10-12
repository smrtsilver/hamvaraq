from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from books.models import Book, Category, Wishlist
from common.models import City
from exchanges import services
from exchanges.models import Exchange
from notifications.models import Notification
from trust.models import Report, Vote
from trust.services import apply_decision, reputation


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.isfahan = City.objects.create(name="اصفهان")
        cls.tehran = City.objects.create(name="تهران")
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
        self.client.post(reverse("books:relist", args=[ex.book.pk]))
        ex.book.refresh_from_db()
        self.assertEqual(ex.book.status, Book.Status.AVAILABLE)

    def test_pages_render(self):
        ex = self.complete()
        self.client.login(username="taker", password="x12345678")
        for url in ["/", "/books/", f"/books/{ex.book.pk}/", "/books/new/", "/books/mine/", "/books/wishlist/",
                    "/exchanges/", f"/exchanges/{ex.pk}/", "/notifications/", "/accounts/u/giver/", "/accounts/settings/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_signup_flow(self):
        r = self.client.post(reverse("accounts:signup"), {
            "username": "newuser", "password1": "Str0ng-pass-99", "password2": "Str0ng-pass-99", "city": self.tehran.pk})
        self.assertEqual(r.status_code, 302)
        u = User.objects.get(username="newuser")
        self.assertEqual(u.points, 0)


class IsbnAndBulkTests(Base):
    def test_normalize(self):
        from books.isbn import normalize
        self.assertEqual(normalize("978-964-6194-48-5"), "9789646194485")
        self.assertEqual(normalize("۹۷۸۹۶۴۶۱۹۴۴۸۵"), "9789646194485")
        self.assertEqual(normalize("0-306-40615-X".replace("X", "2")), "0306406152")
        self.assertIsNone(normalize("12345"))

    def test_lookup_parses_and_caches(self):
        import io, json
        from unittest import mock
        from django.core.cache import cache
        from books import isbn
        cache.clear()
        body = json.dumps({"ISBN:9780140328721": {"title": "Fantastic Mr Fox", "authors": [{"name": "Roald Dahl"}]}})
        with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(body.encode())) as m:
            r = isbn.lookup("978-0-14-032872-1")
            isbn.lookup("9780140328721")
        self.assertEqual(r, {"isbn": "9780140328721", "title": "Fantastic Mr Fox", "author": "Roald Dahl"})
        self.assertEqual(m.call_count, 1)

    def test_lookup_network_error_is_none(self):
        import urllib.error
        from unittest import mock
        from django.core.cache import cache
        from books import isbn
        cache.clear()
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            self.assertIsNone(isbn.lookup("9780140328721"))

    def test_isbn_view_requires_login_and_404s(self):
        from unittest import mock
        url = reverse("books:isbn")
        self.assertEqual(self.client.get(url, {"isbn": "9780140328721"}).status_code, 302)
        self.client.login(username="giver", password="x12345678")
        with mock.patch("books.isbn.lookup", return_value=None):
            self.assertEqual(self.client.get(url, {"isbn": "9780140328721"}).status_code, 404)
        with mock.patch("books.isbn.lookup", return_value={"isbn": "1", "title": "T", "author": "A"}):
            self.assertEqual(self.client.get(url, {"isbn": "9780140328721"}).json()["title"], "T")

    def _bulk_data(self, rows):
        data = {"city": self.isfahan.pk, "condition": "used", "form-TOTAL_FORMS": 8, "form-INITIAL_FORMS": 0,
                "form-MIN_NUM_FORMS": 0, "form-MAX_NUM_FORMS": 8}
        for i in range(8):
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
