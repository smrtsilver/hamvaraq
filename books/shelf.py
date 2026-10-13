"""قفسه‌ی شخصی: افزودن، ویرایش (وضعیت خواندن، نقد، یادداشت) و حذف کتاب‌های خود کاربر."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from common.throttle import throttle

from .forms import ShelfAddForm, ShelfEntryForm
from . import reading
from .models import ReadingGoal, ShelfEntry

SHELF_MAX = 2000


@login_required
def my_shelf(request):
    qs = request.user.shelf.select_related("book")
    tab = request.GET.get("s", "")
    counts = dict(request.user.shelf.values_list("reading_status").annotate(n=Count("id")))
    if tab in ShelfEntry.Reading.values:
        qs = qs.filter(reading_status=tab)
    elif tab == "swap":
        qs = qs.filter(book__isnull=False, book__deleted_at__isnull=True, book__owner=request.user, book__status__in=["available", "reserved"])
    tabs = [("", "همه", sum(counts.values()))] + [(v, label, counts.get(v, 0)) for v, label in ShelfEntry.Reading.choices]
    entries = list(qs[:300])
    matches = reading.wanted_matches(request.user, entries)
    for e in entries:
        e.matches = matches.get(e.pk, [])
    return render(request, "books/shelf.html", {"entries": entries, "tabs": tabs, "tab": tab, "add_form": ShelfAddForm(),
                                                "goal": reading.goal_progress(request.user), "jyear": reading.current_jyear(),
                                                "recs": reading.recommendations(request.user, 8) if not tab else [],
                                                "streak": reading.streak(request.user, 14),
                                                "reading_now": [e for e in entries if e.reading_status == ShelfEntry.Reading.READING][:5]})


@login_required
def shelf_stats(request):
    this = reading.current_jyear()
    try:
        year = int(request.GET.get("y", this))
    except ValueError:
        year = this
    year = max(1300, min(this, year))
    if request.method == "POST":
        try:
            target = int(request.POST.get("target", "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
        except ValueError:
            target = 0
        if 1 <= target <= 500:
            ReadingGoal.objects.update_or_create(user=request.user, year=this, defaults={"target": target})
            messages.success(request, "هدف امسالت ثبت شد. کتاب‌خوندنت پربار!")
        else:
            messages.error(request, "یه عدد بین ۱ تا ۵۰۰ بنویس.")
        return redirect("books:shelf_stats")
    years = sorted({this, *[y for y in ReadingGoal.objects.filter(user=request.user).values_list("year", flat=True)]}, reverse=True)
    return render(request, "books/shelf_stats.html", {"year": year, "this_year": this, "years": years,
                                                      "goal": reading.goal_progress(request.user, year), "stats": reading.reading_stats(request.user, year),
                                                      "streak": reading.streak(request.user, 35)})


@login_required
@throttle("shelfadd", 60, 3600, by="user")
def shelf_add(request):
    initial = {k: request.GET[k][:150] for k in ("title", "author") if request.GET.get(k)}
    form = ShelfAddForm(request.POST or None, initial=initial or None)
    if request.method == "POST":
        if request.user.shelf.count() >= SHELF_MAX:
            messages.error(request, "قفسه‌ات پره؛ چندتا رو حذف کن.")
            return redirect("books:shelf")
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, f"«{entry.title}» به قفسه‌ات اضافه شد.")
            return redirect("books:shelf_edit", entry.pk)
    return render(request, "books/shelf_add.html", {"add_form": form})


@login_required
def shelf_edit(request, pk):
    entry = get_object_or_404(ShelfEntry.objects.select_related("book"), pk=pk, user=request.user)
    form = ShelfEntryForm(request.POST or None, request.FILES or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "ذخیره شد.")
        return redirect("books:shelf_edit", pk)
    return render(request, "books/shelf_edit.html", {"entry": entry, "form": form})


@login_required
@require_POST
def shelf_delete(request, pk):
    entry = get_object_or_404(ShelfEntry.objects.select_related("book"), pk=pk, user=request.user)
    if entry.for_exchange:
        messages.error(request, "این کتاب الان برای معاوضه گذاشته شده؛ اول از معاوضه برش دار.")
        return redirect("books:shelf_edit", pk)
    entry.delete()
    messages.success(request, "از قفسه برداشته شد.")
    return redirect("books:shelf")


@login_required
@require_POST
def mark_today(request):
    from django.utils import timezone

    from .models import ReadingDay

    entry = request.user.shelf.filter(pk=request.POST.get("entry") or 0).first()
    ReadingDay.objects.get_or_create(user=request.user, day=timezone.localdate(), defaults={"entry": entry})
    messages.success(request, "ثبت شد؛ سری خوندنت ادامه داره.")
    return redirect("books:shelf_stats" if request.POST.get("next") == "stats" else "books:shelf")


@login_required
def highlights(request):
    from .forms import HighlightForm
    from .models import Highlight

    form = HighlightForm(request.POST or None, user=request.user,
                         initial={k: request.GET[k][:600] for k in ("text", "title", "author") if request.GET.get(k)} or None)
    if request.method == "POST" and form.is_valid():
        if Highlight.objects.filter(user=request.user).count() >= 3000:
            messages.error(request, "تعداد نقل‌قول‌هات به سقف رسیده.")
        else:
            h = form.save(commit=False)
            h.user = request.user
            if h.entry and not h.title:
                h.title, h.author = h.entry.title, h.entry.author
            h.save()
            messages.success(request, "نقل‌قول ذخیره شد.")
        return redirect("books:highlights")
    items = list(Highlight.objects.filter(user=request.user).select_related("entry")[:500])
    groups = {}
    for h in items:
        groups.setdefault((h.title, h.author), []).append(h)
    return render(request, "books/highlights.html", {"form": form, "groups": list(groups.items()), "count": len(items)})


@login_required
@require_POST
def highlight_delete(request, pk):
    from .models import Highlight

    get_object_or_404(Highlight, pk=pk, user=request.user).delete()
    return redirect("books:highlights")


@login_required
def shelf_export(request):
    """خروجی CSV قفسه (با BOM تا اکسل فارسی رو درست نشون بده) یا نسخه‌ی چاپی (?print=1) برای ذخیره به PDF."""
    import csv

    from django.http import HttpResponse

    from common.jalali import jdate

    entries = request.user.shelf.select_related("book").order_by("title")
    if request.GET.get("print"):
        return render(request, "books/shelf_print.html", {"entries": entries, "count": entries.count()})
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="hamvaraq-shelf.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    w.writerow(["عنوان", "نویسنده", "شابک", "وضعیت خواندن", "تاریخ تموم کردن", "ستاره", "نقد", "یادداشت", "برای معاوضه", "تاریخ افزودن"])
    for e in entries:
        w.writerow([e.title, e.author, e.isbn, e.get_reading_status_display(), jdate(e.finished_at) if e.finished_at else "",
                    e.rating or "", e.review, e.note, "بله" if e.for_exchange else "خیر", jdate(e.created_at)])
    return resp
