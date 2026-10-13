"""صفحه‌های نویسنده و ناشر برای سئو: /authors/ ، /authors/<slug>/ ، /publishers/ ، /publishers/<slug>/ (بر پایه‌ی کتاب‌های قابل دیدن)."""

import json
from collections import Counter

from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from .listing import decorate_cards
from .models import Book

PER_PAGE = 24


def _display_name(names):
    """رایج‌ترین نوشتار یک نام (کاربرها یه نویسنده رو کمی متفاوت می‌نویسن)."""
    return Counter(" ".join(n.split()) for n in names if n and n.strip()).most_common(1)[0][0]


def _listing(request, qs, slug_field, kind, title, intro, name_of):
    rows = list(qs.exclude(**{slug_field: ""}).values(slug_field).annotate(n=Count("id")).order_by("-n", slug_field))
    page = Paginator(rows, 48).get_page(request.GET.get("page"))
    names = name_of([r[slug_field] for r in page])
    items = [{"slug": r[slug_field], "name": names.get(r[slug_field], r[slug_field]), "n": r["n"]} for r in page]
    return render(request, "books/facet_list.html", {"kind": kind, "title": title, "intro": intro, "items": items, "page": page, "qs": ""})


def author_list(request):
    qs = Book.objects.filter(status=Book.Status.AVAILABLE)

    def names(slugs):
        out = {}
        for slug, author in Book.objects.filter(author_slug__in=slugs).values_list("author_slug", "author"):
            out.setdefault(slug, []).append(author)
        return {s: _display_name(v) for s, v in out.items()}
    return _listing(request, qs, "author_slug", "authors", "نویسنده‌ها", "نویسنده‌هایی که کتابشون الان برای مبادله‌ی رایگان تو هم‌ورق هست.", names)


def publisher_list(request):
    qs = Book.objects.filter(status=Book.Status.AVAILABLE, edition__publisher_slug__gt="")

    def names(slugs):
        from .models import Edition
        out = {}
        for slug, name in Edition.objects.filter(publisher_slug__in=slugs).values_list("publisher_slug", "publisher"):
            out.setdefault(slug, []).append(name)
        return {s: _display_name(v) for s, v in out.items()}
    rows = list(qs.values("edition__publisher_slug").annotate(n=Count("id")).order_by("-n", "edition__publisher_slug"))
    page = Paginator(rows, 48).get_page(request.GET.get("page"))
    slugs = [r["edition__publisher_slug"] for r in page]
    display = names(slugs)
    items = [{"slug": r["edition__publisher_slug"], "name": display.get(r["edition__publisher_slug"], r["edition__publisher_slug"]), "n": r["n"]} for r in page]
    return render(request, "books/facet_list.html", {"kind": "publishers", "title": "ناشران", "intro": "ناشرهایی که کتابشون الان برای مبادله‌ی رایگان تو هم‌ورق هست.", "items": items, "page": page, "qs": ""})


def _detail(request, qs, kind, name, url, desc, ld_type):
    page = Paginator(qs.select_related("city__province", "owner", "edition").order_by("status", "-created_at"), PER_PAGE).get_page(request.GET.get("page"))
    page.object_list = decorate_cards(page.object_list, request.user)
    ld = {"@context": "https://schema.org", "@type": ld_type, "name": name, "url": request.build_absolute_uri(url)}
    return render(request, "books/facet_detail.html", {
        "kind": kind, "facet_name": name, "page": page, "qs": "", "desc": desc, "count": page.paginator.count,
        "ld_json": json.dumps(ld, ensure_ascii=False).replace("<", "\\u003c")})


def author_detail(request, slug):
    qs = Book.objects.filter(author_slug=slug).exclude(status=Book.Status.EXCHANGED)
    if not qs.exists():
        raise Http404
    name = _display_name(qs.values_list("author", flat=True))
    return _detail(request, qs, "authors", name, reverse("author", args=[slug]),
                   f"کتاب‌های {name} برای مبادله‌ی رایگان؛ بخوان، بسپار، دوباره بخوان تو هم‌ورق.", "Person")


def publisher_detail(request, slug):
    qs = Book.objects.filter(edition__publisher_slug=slug).exclude(status=Book.Status.EXCHANGED)
    if not qs.exists():
        raise Http404
    name = _display_name(qs.values_list("edition__publisher", flat=True))
    return _detail(request, qs, "publishers", name, reverse("publisher", args=[slug]),
                   f"کتاب‌های منتشرشده توسط {name} برای مبادله‌ی رایگان تو هم‌ورق.", "Organization")
