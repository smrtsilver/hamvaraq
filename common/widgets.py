"""انتخاب تاریخ و ساعت جلالی (سال/ماه/روز + ساعت)؛ مقدار نهایی datetime میلادیِ آگاه از منطقه‌ی زمانی."""


import jdatetime
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .jalali import MONTHS, fa_digits


class JalaliDateTimeWidget(forms.MultiWidget):
    template_name = "forms/jalali_datetime.html"

    def __init__(self, attrs=None, years_back=0, years_ahead=3):
        year = jdatetime.date.today().year
        years = [("", "سال"), *[(str(y), fa_digits(y)) for y in range(year - years_back, year + years_ahead + 1)]]
        months = [("", "ماه"), *[(str(i), name) for i, name in enumerate(MONTHS, start=1)]]
        days = [("", "روز"), *[(str(d), fa_digits(d)) for d in range(1, 32)]]
        widgets = (
            forms.Select(choices=years, attrs={"aria-label": "سال"}),
            forms.Select(choices=months, attrs={"aria-label": "ماه"}),
            forms.Select(choices=days, attrs={"aria-label": "روز"}),
            forms.TimeInput(format="%H:%M", attrs={"type": "time", "aria-label": "ساعت"}),
        )
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return ["", "", "", ""]
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        j = jdatetime.datetime.fromgregorian(datetime=value)
        return [str(j.year), str(j.month), str(j.day), f"{j.hour:02d}:{j.minute:02d}"]


class JalaliDateTimeField(forms.Field):
    widget = JalaliDateTimeWidget
    default_error_messages = {"invalid": "تاریخ یا ساعت معتبر نیست.", "incomplete": "سال، ماه و روز رو کامل انتخاب کن."}

    def to_python(self, value):
        if not value or not any(value[:3]):
            return None
        y, m, d, *rest = value
        if not (y and m and d):
            raise ValidationError(self.error_messages["incomplete"], code="incomplete")
        hh, mm = 0, 0
        if rest and rest[0]:
            try:
                hh, mm = (int(x) for x in str(rest[0]).split(":")[:2])
            except ValueError:
                raise ValidationError(self.error_messages["invalid"], code="invalid") from None
        try:
            greg = jdatetime.datetime(int(y), int(m), int(d), hh, mm).togregorian()
        except (ValueError, TypeError):
            raise ValidationError(self.error_messages["invalid"], code="invalid") from None
        return timezone.make_aware(greg, timezone.get_current_timezone())

    def has_changed(self, initial, data):
        return True
