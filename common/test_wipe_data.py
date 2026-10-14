import io
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import User
from books.models import Book, Category
from common.models import City, Province, SiteSetting


class WipeDataTests(TestCase):
    def test_wipes_users_content_and_media_but_keeps_reference_data(self):
        prov = Province.objects.create(name="تهران")
        city = City.objects.create(province=prov, name="تهران")
        cat = Category.objects.create(name="رمان")
        user = User.objects.create_user("sara", password="x", city=city)
        User.objects.create_superuser("boss", password="x")
        Book.objects.create(owner=user, title="بوف کور", author="هدایت", category=cat, city=city)
        settings_before = SiteSetting.objects.count()

        with tempfile.TemporaryDirectory() as media:
            (Path(media) / "books").mkdir()
            (Path(media) / "books" / "a.jpg").write_bytes(b"x")
            with override_settings(MEDIA_ROOT=media):
                call_command("wipe_data", yes=True, no_backup=True, verbosity=0, stdout=io.StringIO())
            self.assertEqual(list(Path(media).iterdir()), [])

        self.assertFalse(User.objects.exists())
        self.assertFalse(Book.objects.exists())
        self.assertTrue(City.objects.filter(pk=city.pk).exists())
        self.assertTrue(Category.objects.filter(pk=cat.pk).exists())
        self.assertGreaterEqual(SiteSetting.objects.count(), settings_before)
