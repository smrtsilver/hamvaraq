from django.db import transaction

from .models import Notification


def notify(user, text, url="", kind=Notification.Kind.SYSTEM):
    """اعلان داخل سایت می‌سازه و (بعد از commit) اگه کاربر Web Push فعال کرده باشه براش می‌فرسته."""
    from . import push

    note = Notification.objects.create(user=user, text=text, url=url, kind=kind)
    transaction.on_commit(lambda: push.dispatch(note))
    return note
