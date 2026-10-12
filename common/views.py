from django.shortcuts import render

from books.models import Book
from exchanges.models import Exchange


def home(request):
    latest = Book.objects.filter(status=Book.Status.AVAILABLE).select_related("city", "category")[:8]
    stats = {
        "books": Book.objects.count(),
        "exchanges": Exchange.objects.filter(status=Exchange.Status.COMPLETED).count(),
    }
    return render(request, "home.html", {"latest": latest, "stats": stats})


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)
