"""فیلدهای «استان ← شهر»: بدون JS هم کار می‌کنه (شهرها با نام استان)، با JS آبشاری و جستجویی می‌شه."""

import time

from django import forms
from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.forms.utils import flatatt
from django.utils.html import escape, format_html, format_html_join
from django.utils.safestring import mark_safe

from .forms import EMPTY_LABEL
from .models import City, Province

# HTML گزینه‌های شهر (~۱۴۵۰ تا) به ازای هر queryset؛ رندرشون با تمپلیت ویجت جنگو ~۲۰۰ms CPU برای هر صفحه بود
_OPTIONS_CACHE = {}
_OPTIONS_TTL = 600  # تغییر از پنل فقط کش همون پروسه رو پاک می‌کنه؛ بقیه‌ی worker ها حداکثر ۱۰ دقیقه بعد


@receiver([post_save, post_delete], sender=City)
@receiver([post_save, post_delete], sender=Province)
def _drop_city_options(**kwargs):
    _OPTIONS_CACHE.clear()


class CitySelect(forms.Select):
    """هر گزینه‌ی شهر شناسه‌ی استانش رو داره تا جاوااسکریپت بتونه فیلتر کنه."""

    def render(self, name, value, attrs=None, renderer=None):
        choices = self.choices
        queryset = getattr(choices, "queryset", None)
        if queryset is None:  # فهرست دستی، نه ModelChoiceField
            return super().render(name, value, attrs, renderer)
        selected = set(self.format_value(value))
        final = {**self.build_attrs(self.attrs, attrs), "name": name}
        empty = choices.field.empty_label
        head = format_html('<option value=""{}>{}</option>', " selected" if "" in selected else "", empty) if empty is not None else ""
        body = self._options_html(queryset, choices.field)
        for v in selected - {""}:
            needle = f'<option value="{escape(v)}" '
            body = body.replace(needle, needle + "selected ", 1)
        return format_html("<select{}>{}{}</select>", flatatt(final), head, mark_safe(body))

    @staticmethod
    def _options_html(queryset, field):
        key = (str(queryset.query), type(field))
        hit = _OPTIONS_CACHE.get(key)
        if hit and not settings.IS_TEST and time.monotonic() - hit[0] < _OPTIONS_TTL:
            return hit[1]
        html = str(format_html_join(
            "", '<option value="{}" data-province="{}" data-name="{}">{}</option>',
            ((c.pk, c.province_id, c.name, field.label_from_instance(c)) for c in queryset),
        ))
        _OPTIONS_CACHE[key] = (time.monotonic(), html)
        return html

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

    def setup_location(self, city=None, province_label="استان", city_label="شهر", after=None, province_ph="جستجوی استان…", city_ph="جستجوی شهر…"):
        required = self.location_required
        self.fields["province"] = forms.ModelChoiceField(
            Province.objects.all(), required=False, label=province_label, empty_label=self.location_empty,
            widget=forms.Select(attrs={"data-location": "province", "data-combobox": "", "data-placeholder": province_ph}),
        )
        self.fields["city"] = CityChoiceField(
            City.objects.select_related("province"), required=required, label=city_label, empty_label=self.location_empty,
            widget=CitySelect(attrs={"data-location": "city", "data-combobox": "", "data-placeholder": city_ph}),
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
