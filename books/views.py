from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db.models import Q

from accounts.badges import check_badges
from exchanges.models import Exchange

from .forms import BookFilterForm, BookForm
from .models import Book, Wishlist
from .services import notify_wishlists


def book_list(request):
    form = BookFilterForm(request.GET)
    qs = Book.objects.exclude(status=Book.Status.EXCHANGED).select_related("city", "category", "owner")
    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            qs = qs.filter(Q(title__icontains=d["q"]) | Q(author__icontains=d["q"]) | Q(isbn__icontains=d["q"]))
        if d["city"]:
            qs = qs.filter(city=d["city"])
        if d["category"]:
            qs = qs.filter(category=d["category"])
        if d["condition"]:
            qs = qs.filter(condition=d["condition"])
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "books/list.html", {"form": form, "page": page, "qs": params.urlencode()})


def book_detail(request, pk):
    book = get_object_or_404(Book.objects.select_related("owner", "city", "category"), pk=pk)
    user = request.user
    my_request = None
    if user.is_authenticated:
        my_request = Exchange.objects.filter(book=book, requester=user, status__in=Exchange.ACTIVE).first()
    ctx = {
        "book": book,
        "notes": book.notes.select_related("author"),
        "journey": book.journey.select_related("from_city", "to_city"),
        "is_owner": user.is_authenticated and book.owner_id == user.pk,
        "my_request": my_request,
        "pending": book.exchanges.filter(status=Exchange.Status.REQUESTED).select_related("requester")
        if user.is_authenticated and book.owner_id == user.pk else [],
    }
    return render(request, "books/detail.html", ctx)


@login_required
def book_create(request):
    initial = {"city": request.user.city_id}
    form = BookForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        book = form.save(commit=False)
        book.owner = request.user
        book.save()
        notify_wishlists(book)
        check_badges(request.user)
        messages.success(request, "کتاب ثبت شد.")
        return redirect("books:detail", book.pk)
    return render(request, "books/form.html", {"form": form, "title": "ثبت کتاب"})


@login_required
def book_edit(request, pk):
    book = get_object_or_404(Book, pk=pk, owner=request.user)
    if book.status == Book.Status.RESERVED:
        messages.error(request, "کتاب رزروشده رو نمی‌شه ویرایش کرد.")
        return redirect("books:detail", pk)
    form = BookForm(request.POST or None, request.FILES or None, instance=book)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("books:detail", pk)
    return render(request, "books/form.html", {"form": form, "title": "ویرایش کتاب"})


@login_required
@require_POST
def book_delete(request, pk):
    book = get_object_or_404(Book, pk=pk, owner=request.user)
    if book.status == Book.Status.RESERVED or book.exchanges.filter(status=Exchange.Status.REQUESTED).exists():
        messages.error(request, "تا درخواست‌های باز بسته نشدن نمی‌شه کتاب رو حذف کرد.")
        return redirect("books:detail", pk)
    book.delete()
    messages.success(request, "کتاب حذف شد.")
    return redirect("books:mine")


@login_required
@require_POST
def book_relist(request, pk):
    """کتابی که تازه گرفتی رو دوباره برای مبادله می‌ذاری."""
    book = get_object_or_404(Book, pk=pk, owner=request.user, status=Book.Status.EXCHANGED)
    if request.user.city_id:
        book.city_id = request.user.city_id
    book.status = Book.Status.AVAILABLE
    book.save(update_fields=["status", "city"])
    notify_wishlists(book)
    check_badges(request.user)
    messages.success(request, "کتاب دوباره تو قفسه‌ی مبادله قرار گرفت.")
    return redirect("books:detail", pk)


@login_required
def my_books(request):
    return render(request, "books/mine.html", {"books": request.user.books.select_related("city")})


@login_required
def wishlist(request):
    if request.method == "POST":
        text = request.POST.get("text", "").strip()[:200]
        if text:
            Wishlist.objects.get_or_create(user=request.user, text=text)
            messages.success(request, "به لیست آرزو اضافه شد؛ اگه ثبت بشه خبرت می‌کنیم.")
        return redirect("books:wishlist")
    return render(request, "books/wishlist.html", {"wishes": request.user.wishes.all()})


@login_required
@require_POST
def wishlist_delete(request, pk):
    get_object_or_404(Wishlist, pk=pk, user=request.user).delete()
    return redirect("books:wishlist")
