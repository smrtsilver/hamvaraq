"""حدس دسته از موضوع‌ها و رده‌ی دیویی، و رسیدنش به فرم (استعلام شابک و جستجوی عنوان)."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from books import iran_isbn
from books import isbn as isbn_lib
from books.categorize import from_dewey, guess_category, guess_category_name
from books.models import Category, Edition


class GuessTests(TestCase):
    def test_subjects_win(self):
        self.assertEqual(guess_category_name(["داستان‌های کره‌ای -- قرن ۲۱م."]), "رمان")
        self.assertEqual(guess_category_name(["ادبیات کودکان", "داستان"]), "کودک و نوجوان")
        self.assertEqual(guess_category_name(["موفقیت -- جنبه‌های روان‌شناسی"]), "روان‌شناسی")
        self.assertEqual(guess_category_name(["شعر فارسی -- قرن ۸ق."]), "شعر")
        self.assertEqual(guess_category_name(["داستان‌های کوتاه فارسی"]), "داستان کوتاه")

    def test_dewey_fallback(self):
        self.assertEqual(from_dewey("۱۵۸/۱"), "روان‌شناسی")
        self.assertEqual(from_dewey("895.735"), "رمان")        # داستان کره‌ای
        self.assertEqual(from_dewey("891/553"), "رمان")        # داستان فارسی
        self.assertEqual(from_dewey("891.551"), "شعر")          # شعر فارسی
        self.assertEqual(from_dewey("813.54"), "رمان")          # داستان آمریکایی
        self.assertEqual(from_dewey("005.1"), "کامپیوتر")
        self.assertEqual(from_dewey("955.084"), "تاریخ")
        self.assertIsNone(from_dewey(""))
        self.assertEqual(from_dewey("۸فا۳/۶۲"), "رمان")          # رده‌ی ادبیات فارسی کتابخانه‌ی ملی
        self.assertEqual(from_dewey("۸فا۱/۳۲"), "شعر")

    def test_unknown_gives_none(self):
        self.assertIsNone(guess_category_name(["چیزی بی‌ربط"], ""))

    def test_only_existing_categories(self):
        Category.objects.get_or_create(name="روان‌شناسی")
        self.assertEqual(guess_category(["موفقیت"]).name, "روان‌شناسی")


class ParseDeweyTests(TestCase):
    def test_opac_and_ketab_carry_dewey_and_subjects(self):
        from books.test_iran_isbn import KETAB_PAGE, OPAC_PAGE, _opac_row

        page = OPAC_PAGE.replace("</table>", _opac_row("رده بندی دیویی", "&#x202d;۱۵۸/۱") + "</table>")
        self.assertIn("۱۵۸/۱", iran_isbn.parse_opac(page, "9786229015155")["dewey"])
        k = KETAB_PAGE.replace("</h1>", '</h1> <p class="card-text"> <small> <span> داستان‌های کره‌ای - قرن 21م. </span> </small> </p>', 1)
        k += '<div class="col-3 py-2 border-bottom border-0 text-muted">کد دیویی</div> <div class="col-9 py-2 border-bottom boldTr">895.735</div>'
        rec = iran_isbn.parse_ketab(k, "9786227992571")
        self.assertEqual((rec["subjects"], rec["dewey"]), (["داستان‌های کره‌ای"], "895.735"))


class FormGetsCategoryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.cat, _ = Category.objects.get_or_create(name="روان‌شناسی")
        self.user = User.objects.create_user("reader", password="x-strong-pass-1")
        self.client.force_login(self.user)

    def test_isbn_lookup_returns_category(self):
        Edition.objects.create(isbn13="9786229015155", title="اسب سیاه", authors=["تاد رز"], source="opac", confidence=90,
                               subjects=["موفقیت -- جنبه‌های روان‌شناسی"], provenance={"dewey": "۱۵۸/۱"})
        d = self.client.get(reverse("books:isbn"), {"isbn": "9786229015155"}).json()
        self.assertEqual(d["category"], {"id": self.cat.pk, "name": "روان‌شناسی"})

    def test_catalog_search_items_have_category_and_isbn(self):
        rec = {"title": "اسب سیاه", "authors": ["تاد رز"], "isbn": "9786229015155", "subjects": ["موفقیت"], "dewey": ""}
        with mock.patch.object(isbn_lib, "nlai_title_search", return_value=[rec]):
            item = self.client.get(reverse("books:catalog_search"), {"q": "اسب سیاه"}).json()["items"][0]
        self.assertEqual((item["isbn"], item["category"]["name"]), ("9786229015155", "روان‌شناسی"))
