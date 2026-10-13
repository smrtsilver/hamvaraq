"""شابک پیدا نشد ← جستجوی عنوان در کتابخانه‌ی ملی، و پاکسازی داده‌ی MARC؛ شمارنده‌ی لایک/دیسلایک اعتبار."""

import urllib.error
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from books import isbn as isbn_lib

RECORD = {"title": "سووشون، آینه روزگار", "subtitle": "تحلیل جامعه‌شناختی", "authors": ["فاطمه سرمشقی", "Fatemeh Sarmashghi"],
          "translators": [], "publisher": "علمی و فرهنگی", "year": 1397, "year_calendar": "jalali", "pages": 426, "isbn": "9786004365758"}


class CatalogSearchViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("reader", password="x-strong-pass-1")
        self.url = reverse("books:catalog_search")

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url, {"q": "سووشون"}).status_code, 302)

    def test_returns_flat_items_with_joined_authors(self):
        self.client.force_login(self.user)
        with mock.patch.object(isbn_lib, "nlai_title_search", return_value=[RECORD]) as search:
            r = self.client.get(self.url, {"q": "سووشون"})
        search.assert_called_once_with("سووشون")
        self.assertEqual(r.status_code, 200)
        item = r.json()["items"][0]
        self.assertEqual(item["author"], "فاطمه سرمشقی، Fatemeh Sarmashghi")
        self.assertEqual((item["publisher"], item["year"], item["pages"], item["isbn"]), ("علمی و فرهنگی", 1397, 426, "9786004365758"))

    def test_source_down_is_a_friendly_503(self):
        self.client.force_login(self.user)
        with mock.patch.object(isbn_lib, "nlai_title_search", side_effect=urllib.error.URLError("down")):
            r = self.client.get(self.url, {"q": "سووشون"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("message", r.json())

    def test_isbn_input_points_to_catalog_search(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("books:create")).content.decode()
        self.assertIn(f'data-catalog-url="{self.url}"', html)


class NlaiTitleSearchTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_short_query_makes_no_request(self):
        with mock.patch.object(isbn_lib, "_get") as get:
            self.assertEqual(isbn_lib.nlai_title_search("ab"), [])
        get.assert_not_called()

    def test_results_are_cached(self):
        page = b'<a href="/bibliography/abc1/x">x</a>'
        with mock.patch.object(isbn_lib, "_get", side_effect=[page, b""]) as get, \
             mock.patch.object(isbn_lib, "parse_marc", return_value=[{"marker": 1}]), \
             mock.patch.object(isbn_lib, "_marc_record", return_value={"title": "سووشون"}):
            first = isbn_lib.nlai_title_search("سووشون")
            second = isbn_lib.nlai_title_search("سووشون")
        self.assertEqual(first, [{"title": "سووشون"}])
        self.assertEqual(second, first)
        self.assertEqual(get.call_count, 2)          # جستجو + MARC، فقط بار اول


class MarcCleanTests(TestCase):
    def test_zero_width_joiners_and_edge_zwnj_removed(self):
        self.assertEqual(isbn_lib._clean("م‍ن‍ی‍ژه‌ م‍ح‍ام‍دی‌"), "منیژه محامدی")

    def test_inner_zwnj_kept(self):
        self.assertEqual(isbn_lib._clean("نیم‌فاصله‌ها"), "نیم‌فاصله‌ها")


class ReputationCountsTests(TestCase):
    def test_newcomer_has_zero_counts(self):
        from trust.services import reputation

        rep = reputation(User.objects.create_user("fresh", password="x-strong-pass-1"))
        self.assertEqual((rep["likes"], rep["dislikes"]), (0, 0))
