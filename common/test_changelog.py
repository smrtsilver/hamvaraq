"""تاریخچه‌ی نسخه‌ها: صفحه، لینک فوتر، و گره خوردن نسخه به کش سرویس‌ورکر (عوض شدن نسخه ← کش قبلی پاک)."""

from django.test import TestCase
from django.urls import reverse

from common.releases import APP_VERSION, RELEASES


class ChangelogTests(TestCase):
    def test_page_lists_releases_newest_first(self):
        r = self.client.get(reverse("changelog"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(RELEASES[0]["title"], html)
        self.assertLess(html.index(RELEASES[0]["title"]), html.index(RELEASES[-1]["title"]))

    def test_current_version_is_first_release(self):
        self.assertEqual(APP_VERSION, RELEASES[0]["version"])
        versions = [tuple(int(x) for x in r["version"].split(".")) for r in RELEASES]
        self.assertEqual(versions, sorted(versions, reverse=True))

    def test_footer_links_changelog_and_body_has_version(self):
        html = self.client.get("/").content.decode()
        self.assertIn(reverse("changelog"), html)
        self.assertIn(f'data-version="{APP_VERSION}"', html)

    def test_service_worker_cache_is_versioned(self):
        body = self.client.get("/sw.js").content.decode()
        self.assertIn(f'const VERSION = "{APP_VERSION}-', body)
        self.assertIn("skipWaiting()", body)
