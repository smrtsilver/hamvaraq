"""فیلدهای «استان ← شهر»: بدون JS هم کار می‌کنه (شهرها با نام استان)، با JS آبشاری و جستجویی می‌شه."""

from django import forms

from .forms import EMPTY_LABEL
from .models import City, Province


class CitySelect(forms.Select):
    """هر گزینه‌ی شهر شناسه‌ی استانش رو داره تا جاوااسکریپت بتونه فیلتر کنه."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-province"] = instance.province_id
            option["attrs"]["data-name"] = instance.name
        return option


class CityChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.full_name


class LocationMixin:
    """
    به فرم دو فیلد `province` و `city` اضافه می‌کنه (بعد از صدا زدن setup_location) و تطابقشون رو چک می‌کنه.
    `location_required`: برای ثبت کتاب True، برای پروفایل/فیلتر False. استان همیشه اختیاریه چون از شهر مشخص می‌شه
    (کاربر می‌تونه مستقیم شهر رو جستجو کنه).
    """

    location_required = True
    location_empty = EMPTY_LABEL

    def setup_location(self, city=None, province_label="استان", city_label="شهر", after=None):
        required = self.location_required
        self.fields["province"] = forms.ModelChoiceField(
            Province.objects.all(), required=False, label=province_label, empty_label=self.location_empty,
            widget=forms.Select(attrs={"data-location": "province", "data-combobox": "", "data-placeholder": "جستجوی استان…"}),
        )
        self.fields["city"] = CityChoiceField(
            City.objects.select_related("province"), required=required, label=city_label, empty_label=self.location_empty,
            widget=CitySelect(attrs={"data-location": "city", "data-combobox": "", "data-placeholder": "جستجوی شهر…"}),
        )
        if city is not None:
            self.initial.setdefault("city", city.pk)
            self.initial.setdefault("province", city.province_id)
        # ترتیب: استان و شهر بعد از فیلد `after` (یا آخر فرم)
        others = [n for n in self.fields if n not in ("province", "city")]
        at = others.index(after) + 1 if after in others else len(others)
        self.order_fields([*others[:at], "province", "city", *others[at:]])

    province_only_ok = False  # فیلتر لیست: فقط استان هم معتبره

    def clean_location(self, cleaned):
        province, city = cleaned.get("province"), cleaned.get("city")
        if city and province and city.province_id != province.pk:
            self.add_error("city", "این شهر تو استان انتخاب‌شده نیست.")
        elif province and not city and not self.province_only_ok and "city" not in self.errors:
            self.add_error("city", "شهر رو هم انتخاب کن.")
        elif city and not province:
            cleaned["province"] = city.province  # شهر به‌تنهایی کافیه
        return cleaned
