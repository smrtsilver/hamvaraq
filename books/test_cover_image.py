"""عکس جلد منبع از مسیر امن سایت: فقط دامنه‌های مجاز، فقط تصویر واقعی، با کش."""

import io
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from accounts.models import User
from books import iran_isbn
from books.models import Edition


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), (120, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class CoverImageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(User.objects.create_user("reader", password="x-strong-pass-1"))

    def _edition(self, url):
        return Edition.objects.create(isbn13="9786227992571", title="بادام", source="ketab", confidence=90, cover_url=url)

    def test_serves_allowed_host_image_and_caches(self):
        self._edition("https://pic.ketab.ir/DataBase/BookImages/01/14010616043.jpg")
        url = reverse("books:cover_image", args=["978-622-7992-57-1"])
        with mock.patch("urllib.request.urlopen", return_value=_Resp(_jpeg())) as op:
            r1 = self.client.get(url)
            r2 = self.client.get(url)
        self.assertEqual((r1.status_code, r1["Content-Type"]), (200, "image/jpeg"))
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(op.call_count, 1)

    def test_other_hosts_are_refused(self):
        self._edition("https://evil.example.com/x.jpg")
        with mock.patch("urllib.request.urlopen") as op:
            self.assertEqual(self.client.get(reverse("books:cover_image", args=["9786227992571"])).status_code, 404)
        op.assert_not_called()

    def test_non_image_is_refused(self):
        self._edition("https://pic.ketab.ir/x.jpg")
        with mock.patch("urllib.request.urlopen", return_value=_Resp(b"<html>not an image</html>")):
            self.assertEqual(self.client.get(reverse("books:cover_image", args=["9786227992571"])).status_code, 404)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("books:cover_image", args=["9786227992571"])).status_code, 302)


class KetabCoverParseTests(TestCase):
    def test_cover_url_extracted(self):
        from books.test_iran_isbn import KETAB_PAGE

        page = '<img src="https://pic.ketab.ir/DataBase/BookImages/01/14010616043.jpg" alt="x" class="img-fluid">' + KETAB_PAGE
        self.assertEqual(iran_isbn.parse_ketab(page, "9786227992571")["cover_url"], "https://pic.ketab.ir/DataBase/BookImages/01/14010616043.jpg")
