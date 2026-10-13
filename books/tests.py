from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from . import isbn


def marc_record(fields):
    """رکورد ISO2709 کوچیک برای تست. fields: [(tag, 'متن' یا [(کد, مقدار)])]"""
    bodies, directory, pos = [], b"", 0
    for tag, value in fields:
        if isinstance(value, list):
            text = "  " + "".join(f"\x1f{c}{v}" for c, v in value)
        else:
            text = value
        body = text.encode() + b"\x1e"
        directory += f"{tag}{len(body):04d}{pos:05d}".encode("ascii")
        bodies.append(body)
        pos += len(body)
    base = 24 + len(directory) + 1
    leader = f"{base + pos + 1:05d}pam0 22{base:05d} i 450 ".encode("ascii")
    return leader + directory + b"\x1e" + b"".join(bodies) + b"\x1d"


class NlaiLookupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.record = marc_record([
            ("010", [("a", "‏‫: ‬978-600-7547-71-7")]),
            ("200", [("a", "مدارس دوست‌داشتنی"), ("f", "/ مولف کبری صابر.")]),
            ("700", [("a", "صابر"), ("b", "، کبری"), ("f", "۱۳۵۰ -")]),
        ])

    def test_parse_marc(self):
        result = isbn._from_marc(isbn.parse_marc(self.record)[0], "9786007547717")
        self.assertEqual(result, {"isbn": "9786007547717", "title": "مدارس دوست‌داشتنی", "author": "کبری صابر"})

    def test_other_isbn_rejected(self):
        self.assertIsNone(isbn._from_marc(isbn.parse_marc(self.record)[0], "9780000000002"))

    def test_lookup_uses_nlai_first(self):
        page = '<a href="/bibliography/2QwwS1wI/x/">x</a>'.encode()
        with (
            mock.patch.object(isbn, "_get", side_effect=[page, self.record]) as get,
            mock.patch.object(isbn, "_open_library", return_value=None),
            mock.patch.object(isbn, "_google", return_value=None),
        ):
            result = isbn.lookup("۹۷۸-۶۰۰-۷۵۴۷-۷۱-۷")
        self.assertEqual(result["title"], "مدارس دوست‌داشتنی")
        self.assertEqual(get.call_count, 2)

    def test_network_error_not_cached(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError), mock.patch.object(isbn, "_get", side_effect=OSError):
            self.assertIsNone(isbn.lookup("9786007547717"))
        self.assertIsNone(cache.get("isbn:9786007547717"))
