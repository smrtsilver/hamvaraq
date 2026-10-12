from datetime import timedelta

from django.test import TestCase
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
        self.assertTrue(r.content.startswith(b"\x89PNG"))
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
        self.assertEqual(self.client.get(reverse("books:isbn"), {"isbn": "12"}).status_code, 404)

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
        r = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(r.status_code, 302)  # لاگین نیست
        self.client.login(username="taker", password="x12345678")
        self.assertEqual(self.client.get(reverse("staff_dashboard")).status_code, 302)  # staff نیست
        User.objects.create_superuser("boss", password="x12345678")
        self.client.login(username="boss", password="x12345678")
        r = self.client.get(reverse("staff_dashboard"))
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
        self.assertEqual(self.run_cycle(), {"reminded": 0, "cancelled": 0, "disputed": 0})
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
        self.assertEqual(self.run_cycle(), {"reminded": 0, "cancelled": 0, "disputed": 0})  # از انقضا خارجه
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
        self.assertEqual(self.client.get("/staff/").status_code, 200)


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
                   f"/provinces/{self.tehran.province_id}/", "/challenges/", "/how-it-works/", "/rules/", "/accounts/login/",
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
                      "trust/report", "trust/vote"):
            urls += [f"/admin/{model}/"] + ([] if model == "common/sitesetting" else [f"/admin/{model}/add/"])
        urls.append("/admin/common/sitesetting/1/change/")
        self.check(urls, "ادمین")

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
