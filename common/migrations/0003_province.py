import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("common", "0002_meetingpoint")]

    operations = [
        migrations.CreateModel(
            name="Province",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="نام استان")),
            ],
            options={"verbose_name": "استان", "verbose_name_plural": "استان‌ها", "ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="city",
            name="province",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="cities",
                                    to="common.province", verbose_name="استان"),
        ),
    ]
