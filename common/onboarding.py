"""چک‌لیست شروع برای کاربر واردشده؛ هر قدم از روی داده‌های واقعی تیک می‌خوره."""

from django.db.models import Q
from django.urls import reverse

from books.models import Book, Wishlist
from exchanges.models import Exchange


def steps(user):
    done_exchange = Exchange.objects.filter(Q(owner=user) | Q(requester=user), status=Exchange.Status.COMPLETED).exists()
    return [
        {"title": "شهرت رو انتخاب کن", "hint": "تا کتاب‌های نزدیک خودت و نقطه‌های تحویل شهرت پیشنهاد بشه.",
         "done": bool(user.city_id), "url": reverse("accounts:settings"), "cta": "تنظیمات"},
        {"title": "یه کتاب تو قفسه‌ات بذار", "hint": "کتابی که خوندی و جا نداره؛ هر کتابی که بدی ۱ امتیاز می‌گیری.",
         "done": Book.objects.filter(owner=user).exists() or Exchange.objects.filter(owner=user).exists(),
         "url": reverse("books:create"), "cta": "ثبت کتاب"},
        {"title": "اولین کتابت رو درخواست بده", "hint": "با امتیازت یه کتاب بگیر؛ صاحبش تأیید می‌کنه و تو چت هماهنگ می‌کنید.",
         "done": Exchange.objects.filter(requester=user).exists(), "url": reverse("books:list"), "cta": "دیدن کتاب‌ها"},
        {"title": "اولین مبادله‌ات رو کامل کن", "hint": "بعد از تحویل هر دو طرف تأیید می‌کنید و به هم رأی می‌دید.",
         "done": done_exchange, "url": reverse("exchanges:list"), "cta": "مبادله‌های من"},
        {"title": "کتاب دلخواهت رو تو لیست آرزو بذار", "hint": "هر وقت کسی همون کتاب رو ثبت کرد خبرت می‌کنیم.",
         "done": Wishlist.objects.filter(user=user).exists(), "url": reverse("books:wishlist"), "cta": "لیست آرزو"},
    ]


def progress(user):
    items = steps(user)
    return {"steps": items, "done": sum(s["done"] for s in items), "total": len(items),
            "complete": all(s["done"] for s in items)}
