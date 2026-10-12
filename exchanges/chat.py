"""پیام‌های خوانده‌نشده و خوندن چت."""

from django.db.models import Count, F, Q
from django.utils import timezone

from .models import Exchange


def with_unread(qs, user):
    """به هر مبادله‌ی کاربر `unread` (تعداد پیام‌های خوانده‌نشده از طرف مقابل) اضافه می‌کنه."""
    qs = qs.annotate(
        _unread_owner=Count(
            "messages",
            filter=Q(owner=user) & ~Q(messages__sender=user)
            & (Q(owner_read_at__isnull=True) | Q(messages__created_at__gt=F("owner_read_at"))),
        ),
        _unread_requester=Count(
            "messages",
            filter=Q(requester=user) & ~Q(messages__sender=user)
            & (Q(requester_read_at__isnull=True) | Q(messages__created_at__gt=F("requester_read_at"))),
        ),
    )
    return qs


def unread_of(exchange):
    return exchange._unread_owner + exchange._unread_requester


def total_unread(user):
    qs = with_unread(Exchange.objects.filter(Q(owner=user) | Q(requester=user)), user)
    return sum(unread_of(e) for e in qs.only("id"))


def mark_read(exchange, user):
    field = "owner_read_at" if user.pk == exchange.owner_id else "requester_read_at"
    Exchange.objects.filter(pk=exchange.pk).update(**{field: timezone.now()})
