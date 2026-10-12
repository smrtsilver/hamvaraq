from django import template

from trust.services import reputation

register = template.Library()


@register.inclusion_tag("trust/_reputation.html")
def reputation_badge(user):
    return {"rep": reputation(user)}
