from django.conf import settings
from django.contrib import messages
from django.forms import formset_factory
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Avg, Count

from accounts.badges import check_badges
from django.utils import timezone
from posts.forms import books_of
from common.throttle import throttle
from common.text import words
from exchanges.models import Exchange

from . import card as book_card
from . import isbn as isbn_lookup
from .forms import BookFilterForm, BookForm, BulkCommonForm, BulkRowForm, RelistForm, ReviewForm
from .models import Book, BookPhoto, Review, Wishlist
from .services import notify_wishlists, similar_books


def book_list(request):
    form = BookFilterForm(request.GET)
    qs = Book.objects.exclude(status=Book.Status.EXCHANGED).select_related("city__province", "category", "owner")
    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            # هر کلمه‌ی جستجو باید جایی تو عنوان/نویسنده/شابک باشه (متن نرمال‌شده)
            for word in words(d["q"]):
                qs = qs.filter(search_text__contains=word)
        if d["city"]:
            qs = qs.filter(city=d["city"])
        elif d["province"]:
            qs = qs.filter(city__province=d["province"])
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
    can_review = user.is_authenticated and _can_review(book, user)
    my_review = book.reviews.filter(user=user).first() if user.is_authenticated else None
    ctx = {
        "book": book,
        "ld_json": _book_ld(book, request),
        "photos": book.photos.all(),
        "posts": book.posts.filter(status="published", published_at__lte=timezone.now()).select_related("author")[:3],
        "can_write_post": user.is_authenticated and books_of(user).filter(pk=book.pk).exists(),
        "reviews": book.reviews.select_related("user"),
        "rating": book.reviews.aggregate(avg=Avg("stars"), n=Count("id")),
        "review_form": ReviewForm(instance=my_review) if can_review else None,
        "my_review": my_review,
        "similar": similar_books(book),
        "notes": book.notes.select_related("author"),
        "journey": book.journey.select_related("from_city", "to_city"),
        "is_owner": user.is_authenticated and book.owner_id == user.pk,
        "my_request": my_request,
        "pending": book.exchanges.filter(status=Exchange.Status.REQUESTED).select_related("requester")
        if user.is_authenticated and book.owner_id == user.pk else [],
    }
    return render(request, "books/detail.html", ctx)


def _default_city(user):
    """شهر پیش‌فرض ثبت کتاب: شهر پروفایل، وگرنه شهر آخرین کتابی که ثبت کرده."""
    if user.city_id:
        return user.city
    last = user.books.select_related("city__province").order_by("-created_at").first()
    return last.city if last else None


@login_required
@throttle("bookcreate", 40, 3600, by="user")
def book_create(request):
    form = BookForm(request.POST or None, request.FILES or None, default_city=_default_city(request.user))
    if request.method == "POST" and form.is_valid():
        book = form.save(commit=False)
        book.owner = request.user
        book.save()
        form.save_extra_photos(book)
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
def book_relist(request, pk):
    """کتابی که تازه گرفتی رو دوباره برای مبادله می‌ذاری؛ شهر فعلیت رو تأیید یا عوض می‌کنی."""
    book = get_object_or_404(Book, pk=pk, owner=request.user, status=Book.Status.EXCHANGED)
    form = RelistForm(request.POST or None, default_city=request.user.city or book.city)
    if request.method == "POST" and form.is_valid():
        city = form.cleaned_data["city"]
        book.city, book.status = city, Book.Status.AVAILABLE
        book.save(update_fields=["status", "city"])
        # قدم آخر «مسیر کتاب» اگه مقصدش نامعلوم مونده بود، حالا معلومه
        step = book.journey.order_by("-date").first()
        if step and step.to_city_id is None:
            step.to_city = city
            step.save(update_fields=["to_city"])
        notify_wishlists(book)
        check_badges(request.user)
        messages.success(request, "کتاب دوباره تو قفسه‌ی مبادله قرار گرفت.")
        return redirect("books:detail", pk)
    return render(request, "books/relist.html", {"book": book, "form": form})


@login_required
def my_books(request):
    return render(request, "books/mine.html", {"books": request.user.books.select_related("city")})


@login_required
def wishlist(request):
    if not settings.WISHLIST_ENABLED:
        return render(request, "books/wishlist.html", {"wishes": []})
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
    if not settings.WISHLIST_ENABLED:
        return redirect("books:wishlist")
    get_object_or_404(Wishlist, pk=pk, user=request.user).delete()
    return redirect("books:wishlist")


BULK_ROWS = 8


@login_required
@throttle("bookbulk", 10, 3600, by="user")
def book_bulk_create(request):
    """چند کتاب پشت هم؛ ردیف‌های کاملاً خالی نادیده گرفته می‌شن."""
    RowSet = formset_factory(BulkRowForm, extra=BULK_ROWS, max_num=BULK_ROWS, validate_max=True)
    common = BulkCommonForm(request.POST or None, default_city=_default_city(request.user))
    rows = RowSet(request.POST or None)
    if request.method == "POST" and common.is_valid() and rows.is_valid():
        filled = [f.cleaned_data for f in rows if f.cleaned_data.get("title")]
        if not filled:
            messages.error(request, "حداقل یه کتاب وارد کن.")
        else:
            with transaction.atomic():
                books = [Book.objects.create(
                    owner=request.user, city=common.cleaned_data["city"],
                    condition=common.cleaned_data["condition"], title=r["title"], author=r["author"],
                    isbn=r["isbn"], category=r["category"]) for r in filled]
            for book in books:
                notify_wishlists(book)
            check_badges(request.user)
            messages.success(request, f"{len(books)} کتاب ثبت شد.")
            return redirect("books:mine")
    return render(request, "books/bulk.html", {"common": common, "rows": rows})


@login_required
@throttle("isbn", 30, 60, by="user", methods=("GET",), json=True)
def isbn_view(request):
    result = isbn_lookup.lookup(request.GET.get("isbn", ""))
    if not result:
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(result)


def _can_review(book, user):
    """فقط گیرنده‌ی کتاب در یه مبادله‌ی کامل‌شده (نه صاحب اولیه) نقد می‌نویسه."""
    return Exchange.objects.filter(book=book, requester=user, status=Exchange.Status.COMPLETED).exists()


@login_required
@require_POST
def review_save(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if not _can_review(book, request.user):
        messages.error(request, "فقط کسی که این کتاب رو از طریق هم‌ورق گرفته می‌تونه نقد بنویسه.")
        return redirect("books:detail", pk)
    form = ReviewForm(request.POST, instance=Review.objects.filter(book=book, user=request.user).first())
    if form.is_valid():
        review = form.save(commit=False)
        review.book, review.user = book, request.user
        review.save()
        messages.success(request, "نقدت ثبت شد.")
    else:
        messages.error(request, "ستاره‌ی ۱ تا ۵ رو انتخاب کن.")
    return redirect("books:detail", pk)


def book_card_png(request, pk):
    book = get_object_or_404(Book.objects.select_related("city"), pk=pk)
    resp = HttpResponse(book_card.render_card(book), content_type="image/png")
    if request.GET.get("download"):
        resp["Content-Disposition"] = f'attachment; filename="hamvaraq-book-{book.pk}.png"'
    resp["Cache-Control"] = "public, max-age=300"
    return resp


def _book_ld(book, request):
    """داده‌ی ساخت‌یافته‌ی schema.org برای موتورهای جستجو (< ها escape می‌شن تا از تگ script خارج نشه)."""
    import json

    data = {
        "@context": "https://schema.org", "@type": "Book", "name": book.title,
        "author": {"@type": "Person", "name": book.author},
        "url": request.build_absolute_uri(),
    }
    if book.isbn:
        data["isbn"] = book.isbn
    if book.cover:
        data["image"] = request.build_absolute_uri(book.cover.url)
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


@login_required
@require_POST
def photo_delete(request, pk):
    photo = get_object_or_404(BookPhoto.objects.select_related("book"), pk=pk, book__owner=request.user)
    book_pk = photo.book_id
    photo.image.delete(save=False)
    photo.delete()
    messages.success(request, "عکس حذف شد.")
    return redirect("books:edit", book_pk)


@throttle("suggest", 90, 60, by="auto", methods=("GET",), json=True)
def suggest(request):
    """پیشنهاد عنوان یا نویسنده هنگام تایپ، از کتاب‌های موجود تو سایت (kind=title|author)."""
    kind = request.GET.get("kind", "title")
    ws = words(request.GET.get("q", ""))
    if not ws or sum(len(w) for w in ws) < 2:
        return JsonResponse({"items": []})
    qs = Book.objects.all()
    for w in ws:
        qs = qs.filter(search_text__contains=w)
    if kind == "author":
        rows = qs.order_by("author").values_list("author", flat=True).distinct()[:8]
        return JsonResponse({"items": [{"author": a} for a in rows]})
    seen, items = set(), []
    for title, author, isbn in qs.order_by("-created_at").values_list("title", "author", "isbn")[:60]:
        if (title, author) in seen:
            continue
        seen.add((title, author))
        items.append({"title": title, "author": author, "isbn": isbn})
        if len(items) == 8:
            break
    return JsonResponse({"items": items})
