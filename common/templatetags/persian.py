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
