from .models import Notification


def notify(user, text, url=""):
    return Notification.objects.create(user=user, text=text, url=url)
