"""
تنها راه تغییر امتیاز: apply() همزمان User.points (اتمیک با F) و یک ردیف PointEntry (دفتر) می‌نویسه.
audit() تفاوت «مجموع دفتر» و «User.points» رو پیدا می‌کنه؛ reconcile=True با یه ردیف «اصلاح دفتر» برابرشون می‌کنه.
"""

from django.db import transaction
from django.db.models import F, Sum


def apply(user, delta, reason, exchange=None, note=""):
    """user: شیء یا pk. برمی‌گردونه: ردیف دفتر. شیء کاربر (اگه داده شده) هم به‌روز می‌شه."""
    from accounts.models import PointEntry, User

    pk = getattr(user, "pk", user)
    with transaction.atomic():
        User.objects.filter(pk=pk).update(points=F("points") + delta)
        balance = User.objects.filter(pk=pk).values_list("points", flat=True).get()
        entry = PointEntry.objects.create(user_id=pk, delta=delta, reason=reason, exchange=exchange, note=note[:200], balance_after=balance)
    if hasattr(user, "points"):
        user.points = balance
    return entry


def audit(reconcile=False):
    """[(user_id, username, points, ledger_sum)] برای حساب‌های ناهمخوان."""
    from accounts.models import PointEntry, User

    sums = dict(PointEntry.objects.values_list("user_id").annotate(s=Sum("delta")))
    bad = []
    for user in User.objects.only("id", "username", "points").iterator():
        total = sums.get(user.pk, 0)
        if total != user.points:
            bad.append((user.pk, user.username, user.points, total))
            if reconcile:
                PointEntry.objects.create(user_id=user.pk, delta=user.points - total, reason=PointEntry.Reason.RECONCILE,
                                          note=f"دفتر {total} ولی امتیاز {user.points}", balance_after=user.points)
    return bad
