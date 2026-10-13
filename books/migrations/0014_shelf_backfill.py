from django.db import migrations


def backfill(apps, schema_editor):
    """هر کتاب فعلی (آگهی یا کتابِ گرفته‌شده) یه ردیف تو قفسه‌ی صاحبش می‌گیره."""
    Book = apps.get_model("books", "Book")
    ShelfEntry = apps.get_model("books", "ShelfEntry")
    rows = [ShelfEntry(user_id=b.owner_id, book_id=b.pk, edition_id=b.edition_id, title=b.title, author=b.author, isbn=b.isbn, reading_status="read")
            for b in Book.objects.filter(deleted_at__isnull=True).only("pk", "owner_id", "edition_id", "title", "author", "isbn").iterator()]
    ShelfEntry.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("books", "0013_shelf_entry")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
