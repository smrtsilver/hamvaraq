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
                                                "recs": reading.recommendations(request.user, 8) if not tab else []})


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
                                                      "goal": reading.goal_progress(request.user, year), "stats": reading.reading_stats(request.user, year)})


@login_required
@throttle("shelfadd", 60, 3600, by="user")
def shelf_add(request):
    form = ShelfAddForm(request.POST or None)
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
    form = ShelfEntryForm(request.POST or None, instance=entry)
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
