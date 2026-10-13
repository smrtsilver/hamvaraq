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
        other = self.book(title="دور")
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
