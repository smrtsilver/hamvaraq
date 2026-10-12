from django import template

from common import jalali

register = template.Library()

register.filter("fa", jalali.fa_digits)
register.filter("jdate", jalali.jdate)
register.filter("jtime", jalali.jtime)
register.filter("jdatetime", jalali.jdatetime_str)
register.filter("ago", jalali.ago)


@register.filter
def jlong(value):
    return jalali.jdate(value, long=True)


@register.filter
def mod(value, arg):
    """باقی‌مانده؛ برای رنگ آواتار بر اساس شناسه."""
    try:
        return int(value) % int(arg)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def richtext(value):
    from common import richtext as rt

    return rt.render(value)


@register.filter
def jday(value):
    j = jalali._to_j(value)
    return jalali.fa_digits(j.day) if j else ""


@register.filter
def jmonth(value):
    j = jalali._to_j(value)
    return jalali.MONTHS[j.month - 1] if j else ""


@register.filter
def get_item(mapping, key):
    return (mapping or {}).get(key)
