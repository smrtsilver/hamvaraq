"""فاز ۴ طرح بهبود: صفحه‌های نویسنده/ناشر برای سئو."""

import json

from django.urls import reverse

from accounts.models import User
from books import catalog
from books.models import Book
from common.tests import Base
from common.text import first_author, slugify_fa


class SlugTests(Base):
    def test_slugify_and_first_author(self):
        self.assertEqual(slugify_fa("صادق  هدایت"), "صادق-هدایت")
        self.assertEqual(slugify_fa("كلیدر، محمود!"), "کلیدر-محمود")
        self.assertEqual(slugify_fa("محمود دولت‌آبادی"), slugify_fa("محمود دولت آبادی".replace(" آ", "آ")))
        self.assertEqual(first_author("صادق هدایت، دیگری"), "صادق هدایت")
        self.assertEqual(first_author("الف و ب"), "الف")
        self.assertEqual(first_author(""), "")

    def test_book_and_edition_get_slugs_on_save(self):
        b = Book.objects.create(owner=self.giver, title="ک", author="صادق هدایت", city=self.tehran, isbn="9780306406157")
        self.assertEqual(b.author_slug, "صادق-هدایت")
        b.author = "ديگر، همکار"
        b.save()
        self.assertEqual(Book.objects.get(pk=b.pk).author_slug, "دیگر")
        ed = catalog.record_user_entry(self.giver, "9786007547717", "ک", "ن")
        ed.publisher = "نشر ققنوس"
        ed.save()
        self.assertEqual(ed.publisher_slug, "نشر-ققنوس")


class FacetPageTests(Base):
    def setUp(self):
        self.b1 = Book.objects.create(owner=self.giver, title="بوف کور", author="صادق هدایت", city=self.tehran)
        self.b2 = Book.objects.create(owner=self.giver, title="سه قطره خون", author="صادق  هدایت", city=self.isfahan)
        self.b3 = Book.objects.create(owner=self.giver, title="کلیدر", author="محمود دولت‌آبادی", city=self.isfahan)

    def test_author_pages_list_detail_and_name_variants_merge(self):
        r = self.client.get(reverse("authors"))
        self.assertContains(r, "صادق هدایت")
        self.assertContains(r, "۲ کتاب")
        d = self.client.get(reverse("author", args=["صادق-هدایت"]))
        self.assertEqual({b.title for b in d.context["page"]}, {"بوف کور", "سه قطره خون"})
        self.assertContains(d, "<h1>صادق هدایت</h1>")
        self.assertEqual(self.client.get(reverse("author", args=["ناموجود"])).status_code, 404)

    def test_seo_markup_jsonld_description_breadcrumb_and_book_link(self):
        d = self.client.get(reverse("author", args=["صادق-هدایت"]))
        html = d.content.decode()
        ld = json.loads(html.split('application/ld+json">')[1].split("</script>")[0])
        self.assertEqual((ld["@type"], ld["name"]), ("Person", "صادق هدایت"))
        self.assertTrue("کتاب‌های صادق هدایت برای مبادله‌ی رایگان" in html and 'aria-label="مسیر"' in html)
        self.assertTrue(f'href="{reverse("author", args=["صادق-هدایت"])}"' in self.client.get(self.b1.get_absolute_url()).content.decode())

    def test_hidden_banned_exchanged_books_do_not_appear_and_empty_author_404(self):
        User.objects.filter(pk=self.giver.pk).update(status="banned")
        self.assertEqual(self.client.get(reverse("author", args=["صادق-هدایت"])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("authors")), "صادق هدایت")
        User.objects.filter(pk=self.giver.pk).update(status="active")
        Book.objects.filter(pk__in=[self.b1.pk, self.b2.pk]).update(status="exchanged")
        self.assertEqual(self.client.get(reverse("author", args=["صادق-هدایت"])).status_code, 404)

    def test_publisher_pages_via_edition(self):
        ed = catalog.record_user_entry(self.giver, "9786007547717", "کلیدر", "دولت‌آبادی")
        ed.publisher = "نشر فرهنگ معاصر"
        ed.save()
        Book.objects.filter(pk=self.b3.pk).update(edition=ed)
        listing = self.client.get(reverse("publishers"))
        self.assertContains(listing, "نشر فرهنگ معاصر")
        d = self.client.get(reverse("publisher", args=[ed.publisher_slug]))
        self.assertEqual([b.title for b in d.context["page"]], ["کلیدر"])
        html = d.content.decode()
        self.assertTrue('"@type": "Organization"' in html and "منتشرشده توسط نشر فرهنگ معاصر" in html)
        self.assertEqual(self.client.get(reverse("publisher", args=["نامعلوم"])).status_code, 404)

    def test_sitemap_includes_author_and_publisher_urls_and_static_listing_pages(self):
        ed = catalog.record_user_entry(self.giver, "9786007547717", "ک", "ن")
        ed.publisher = "نشر الف"
        ed.save()
        Book.objects.filter(pk=self.b3.pk).update(edition=ed)
        text = "".join(self.client.get(f"/sitemap.xml?section={s}").content.decode() for s in ("authors", "publishers", "static"))
        index = self.client.get("/sitemap.xml").content.decode()
        if "<sitemapindex" in index:
            import re
            text = "".join(self.client.get(re.sub(r"https?://[^/]+", "", u)).content.decode() for u in re.findall(r"<loc>([^<]+)</loc>", index))
        from urllib.parse import quote
        for needle in ("/authors/", "/publishers/", quote("صادق-هدایت"), quote("نشر-الف")):
            self.assertTrue(needle in text, needle)

    def test_pagination_and_footer_links(self):
        for i in range(50):
            Book.objects.create(owner=self.giver, title=f"ک{i}", author=f"نویسنده شماره {i}", city=self.tehran)
        r = self.client.get(reverse("authors"))
        self.assertEqual(len(r.context["items"]), 48)
        self.assertEqual(len(self.client.get(reverse("authors"), {"page": 2}).context["items"]), 4)        # ۲ نویسنده‌ی اصلی + ۵۰ = ۵۲
        home = self.client.get("/").content.decode()
        self.assertTrue(reverse("authors") in home and reverse("publishers") in home)
