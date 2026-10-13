"""منبع‌های ایرانی شابک: خط‌تیره‌گذاری استاندارد، تجزیه‌ی OPAC و خانه‌ی کتاب، و ترتیب/fallback در پایپ‌لاین."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from books import iran_isbn
from books import isbn as isbn_lib


class HyphenTests(TestCase):
    def test_standard_form_from_iran_ranges(self):
        self.assertEqual(iran_isbn.hyphenate("9786229015155"), "978-622-90151-5-5")   # روی جلد غلط چاپ شده: 978-6-22901-515-5
        self.assertEqual(iran_isbn.hyphenate("9786227992571"), "978-622-7992-57-1")
        self.assertEqual(iran_isbn.hyphenate("9786004365758"), "978-600-436-575-8")
        self.assertEqual(iran_isbn.hyphenate("9789643416928"), "978-964-341-692-8")

    def test_other_splits_are_fallbacks(self):
        variants = iran_isbn.hyphen_variants("9786227992571")
        self.assertEqual(variants[0], "978-622-7992-57-1")
        self.assertEqual(len(variants), 5)
        self.assertEqual(len(set(variants)), 5)

    def test_non_iranian_isbn_is_skipped(self):
        self.assertEqual(iran_isbn.hyphen_variants("9780141036144"), [])
        self.assertEqual(iran_isbn.hyphenate("9780141036144"), "9780141036144")


def _opac_row(label, value):
    return f'<TR> <TD width=20% VALIGN=top ALIGN=right>&#x200f;{label}</TD> <TD VALIGN=top align=center>:</TD> <TD VALIGN=top align=right>{value}</TD> </TR>'


OPAC_PAGE = "<table>" + "".join([
    _opac_row("سرشناسه", "رز، تاد، &#x200f;۱۹۷۴&#x200f;-&#x200f; م.<br>Rose, Todd, 1974-"),
    _opac_row("عنوان و نام پديدآور", "اسب سیاه : رسیدن به موفقیت و کامیابی، از مسیری کاملا متفاوت.../تاد رز ، اوگی اوگاس ؛ [مترجم] ساناز محبی ؛ ویراستار محسن نیکو."),
    _opac_row("مشخصات نشر", "تهران: آبیژ، &#x200f;۱۴۰۲."),
    _opac_row("مشخصات ظاهری", "&#x200f;۲۱۶ ص."),
    _opac_row("شابک", "&#x200f;۱۳۸۰۰۰۰ ریال:&#x200f;978-622-90151-5-5"),
    _opac_row("موضوع", "موفقیت -- جنبه‌های روان‌شناسی<br>Success -- Psychological aspects"),
]) + "</table>"


class OpacParseTests(TestCase):
    def test_full_record(self):
        rec = iran_isbn.parse_opac(OPAC_PAGE, "9786229015155")
        self.assertEqual(rec["title"], "اسب سیاه")
        self.assertTrue(rec["subtitle"].startswith("رسیدن به موفقیت"))
        self.assertEqual(rec["authors"], ["تاد رز", "اوگی اوگاس"])
        self.assertEqual(rec["translators"], ["ساناز محبی"])
        self.assertEqual((rec["publisher"], rec["year"], rec["year_calendar"], rec["pages"]), ("آبیژ", 1402, "jalali", 216))
        self.assertEqual(rec["subjects"], ["موفقیت"])

    def test_other_isbn_is_rejected(self):
        self.assertIsNone(iran_isbn.parse_opac(OPAC_PAGE, "9786227992571"))

    def test_role_prefix_stripped_from_names(self):
        page = OPAC_PAGE.replace("تاد رز ، اوگی اوگاس", "نویسنده نمایشنامه منیژه محامدی")
        self.assertEqual(iran_isbn.parse_opac(page, "9786229015155")["authors"], ["منیژه محامدی"])

    def test_main_entry_used_when_no_responsibility(self):
        page = OPAC_PAGE.replace("/تاد رز ، اوگی اوگاس ؛ [مترجم] ساناز محبی ؛ ویراستار محسن نیکو.", "")
        self.assertEqual(iran_isbn.parse_opac(page, "9786229015155")["authors"], ["تاد رز"])


def _ketab_row(label, value):
    return (f'<div class="row"><div class="col-lg-2 col-4 pe-0 border-0 text-muted">{label}</div>'
            f'<div class="col-lg-10 col-8 ps-0 boldTr border-0">{value}</div></div>')


KETAB_PAGE = ('<h1 class="card-title ketabColor text-muted" style="x"> بادام </h1>' + "".join([
    _ketab_row("تاریخ نشر", " 14010616 "),
    _ketab_row("شابک", "978-622-7992-57-1"),
    _ketab_row("ناشر", '<span> <a class="unlink" href="/Publisher/x"> آزرمیدخت </a> </span>'),
    _ketab_row("پدیدآور", '<span style="font-weight:normal"> نويسنده : <a class="unlink" href="/a"> سون ، وون‌-پیونگ </a> - </span>'
                          '<span style="font-weight:normal"> مترجم : <a class="unlink" href="/b"> عبادی ، رویا </a> </span>'),
    _ketab_row("زبان کتاب", "فارسی"),
    _ketab_row("مشخصات", "جلد - 144 صفحه - ترجمه - چاپ 1"),
]))


class KetabParseTests(TestCase):
    def test_full_record(self):
        rec = iran_isbn.parse_ketab(KETAB_PAGE, "9786227992571")
        self.assertEqual(rec["title"], "بادام")
        self.assertEqual(rec["authors"], ["وون‌-پیونگ سون"])
        self.assertEqual(rec["translators"], ["رویا عبادی"])
        self.assertEqual((rec["publisher"], rec["year"], rec["pages"], rec["edition_no"], rec["language"]),
                         ("آزرمیدخت", 1401, 144, "چاپ 1", "فارسی"))

    def test_other_isbn_is_rejected(self):
        self.assertIsNone(iran_isbn.parse_ketab(KETAB_PAGE, "9786229015155"))


OPAC_REC = {"isbn": "9786229015155", "title": "اسب سیاه", "authors": ["تاد رز"], "translators": ["ساناز محبی"],
            "publisher": "آبیژ", "year": 1402, "year_calendar": "jalali", "pages": 216}


@override_settings(ISBN_SOURCES=["opac", "ketab", "nlai", "openlibrary"])
class PipelineOrderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _patch(self, **sources):
        noop = mock.Mock(return_value=None)
        names = {"opac": "_opac", "ketab": "_ketab", "nlai": "_nlai", "openlibrary": "_open_library", "google": "_google"}
        return [mock.patch.object(isbn_lib, fn, sources.get(key, noop)) for key, fn in names.items()]

    def _run(self, **sources):
        patches = self._patch(**sources)
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return isbn_lib.lookup_full("978-622-90151-5-5")

    def test_opac_record_is_used_and_cached(self):
        rec = self._run(opac=mock.Mock(return_value=OPAC_REC))
        self.assertEqual(rec["title"], "اسب سیاه")
        self.assertEqual(rec["author"], "تاد رز")
        self.assertIn("opac", rec["sources"])
        self.assertEqual(cache.get("isbn2:9786229015155")["title"], "اسب سیاه")

    def test_falls_back_to_ketab_when_opac_is_down(self):
        ketab_rec = dict(OPAC_REC, title="اسب سیاه (ketab)")
        rec = self._run(opac=mock.Mock(side_effect=OSError("down")), ketab=mock.Mock(return_value=ketab_rec))
        self.assertEqual(rec["title"], "اسب سیاه (ketab)")
        self.assertEqual(cache.get("isbn2:9786229015155")["title"], "اسب سیاه (ketab)")   # نتیجه‌ی مثبت کش می‌شه (فقط «پیدا نشد» همراه خطا نه)
        self.assertEqual(rec["sources"], ["ketab"])

    def test_opac_wins_merge_priority_over_nlai(self):
        rec = self._run(opac=mock.Mock(return_value=OPAC_REC), nlai=mock.Mock(return_value=dict(OPAC_REC, title="عنوان دیگر")))
        self.assertEqual(rec["title"], "اسب سیاه")

    def test_google_not_queried_unless_enabled(self):
        google = mock.Mock(return_value=None)
        self._run(opac=mock.Mock(return_value=OPAC_REC), google=google)
        google.assert_not_called()
