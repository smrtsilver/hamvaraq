import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("common", "0004_map_existing_cities")]

    operations = [
        migrations.AlterField(
            model_name="city",
            name="province",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cities",
                                    to="common.province", verbose_name="استان"),
        ),
        migrations.AlterField(
            model_name="city", name="name", field=models.CharField(max_length=100, verbose_name="نام شهر"),
        ),
        migrations.AddConstraint(
            model_name="city",
            constraint=models.UniqueConstraint(fields=("province", "name"), name="unique_city_per_province"),
        ),
    ]
