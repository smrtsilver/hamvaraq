"""شهرهای قدیمی (تخت) رو به استان وصل می‌کنه؛ شناسه‌ی شهرها عوض نمی‌شه پس کتاب‌ها و کاربرها سالم می‌مونن."""

from django.db import migrations

OTHER = "سایر"


def _key(text):
    return "".join(str(text).replace("ي", "ی").replace("ك", "ک").replace("‌", "").split())


def forward(apps, schema_editor):
    from common.locations import load_locations

    Province = apps.get_model("common", "Province")
    City = apps.get_model("common", "City")
    pending = list(City.objects.filter(province__isnull=True))
    if not pending:
        return
    lookup = {}
    for province, cities in load_locations().items():
        for city in cities:
            lookup.setdefault(_key(city), province)  # نام تکراری: اولین استان
    for city in pending:
        province_name = lookup.get(_key(city.name), OTHER)
        province, _ = Province.objects.get_or_create(name=province_name)
        city.province = province
        city.save(update_fields=["province"])


class Migration(migrations.Migration):
    dependencies = [("common", "0003_province")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
