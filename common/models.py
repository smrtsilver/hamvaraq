from django.db import models


class City(models.Model):
    name = models.CharField(max_length=80, unique=True, verbose_name="نام شهر")

    class Meta:
        ordering = ["name"]
        verbose_name = "شهر"
        verbose_name_plural = "شهرها"

    def __str__(self):
        return self.name
