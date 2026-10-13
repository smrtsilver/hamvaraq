from django.conf import settings
from django.contrib import messages
from django.forms import formset_factory
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q, Avg, Count

from accounts.badges import check_badges
from django.utils import timezone
from posts.forms import books_of
from common.throttle import throttle
from common.text import words
from exchanges.models import Exchange

from . import card as book_card
from analytics.tracking import track

from . import catalog
from . import isbn as isbn_lookup
from .forms import BookFilterForm, BookForm, BulkCommonForm, BulkRowForm, RelistForm, ReviewForm
from .models import Book, BookPhoto, Review, Wishlist
from .listing import active_chips, decorate_cards
from .quality import WEIGHTS as QUALITY_WEIGHTS
from .quality import listing_quality
from .services import add_wish, demand_for, notify_wishlists, similar_books


def book_list(request):
    form = BookFilterForm(request.GET)
    qs = Book.objects.select_related("city__province", "category", "owner")
    chips, clear_url = [], ""
    d = {}
    if form.is_valid():
        d = form.cleaned_data
        # پیش‌فرض فقط کتاب‌های «موجود»؛ با گزینه‌ی «رزروشده‌ها هم» رزروها هم می‌آن (مبادله‌شده‌ها هیچ‌وقت)
        qs = qs.exclude(status=Book.Status.EXCHANGED) if d.get("all") else qs.filter(status=Book.Status.AVAILABLE)
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
        qs = _sorted(qs, d.get("sort"), request.user)
        chips, clear_url = active_chips(request, {**d, "_condition_choices": form.fields["condition"].choices, "_sort_choices": form.SORTS})
    else:
        qs = qs.filter(status=Book.Status.AVAILABLE)
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    page.object_list = decorate_cards(page.object_list, request.user)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "books/list.html", {
        "form": form, "page": page, "qs": params.urlencode(), "chips": chips, "clear_url": clear_url,
        "can_save_search": settings.WISHLIST_ENABLED and request.user.is_authenticated and bool(d.get("q"))})


def _sorted(qs, sort, user):
    """جدیدترین (پیش‌فرض)، نزدیک‌ترین (هم‌شهری ← هم‌استان ← بقیه؛ بدون شهر مثل جدیدترین)، پرتقاضاترین (درخواست‌های ۹۰ روز اخیر)."""
    from datetime import timedelta

    from django.db.models import Case, Count, IntegerField, Q, Value, When
    from django.utils import timezone

    if sort == "wanted":
        since = timezone.now() - timedelta(days=90)
        return qs.annotate(req_count=Count("exchanges", filter=Q(exchanges__created_at__gte=since))).order_by("-req_count", "-created_at")
    if sort == "near" and user.is_authenticated and user.city_id:
        rank = Case(When(city_id=user.city_id, then=Value(0)), When(city__province_id=user.city.province_id, then=Value(1)), default=Value(2), output_field=IntegerField())
        return qs.annotate(near_rank=rank).order_by("near_rank", "-created_at")
    return qs.order_by("-created_at")


def book_detail(request, pk):
    book = get_object_or_404(Book.objects.select_related("owner", "city", "category"), pk=pk)
    user = request.user
    track(request, "book", book, book.owner_id)
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
        "expire_days": settings.REQUEST_EXPIRE_DAYS,
        "owner_books": decorate_cards(Book.objects.filter(owner=book.owner, status=Book.Status.AVAILABLE).exclude(pk=book.pk).select_related("city__province", "owner")[:4], user),
        "demand": demand_for(book.isbn, book.title, book.author, exclude_user=book.owner),
        "quality": listing_quality(book) if user.is_authenticated and book.owner_id == user.pk else None,
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
    from .models import ShelfEntry

    sid = request.POST.get("shelf") or request.GET.get("shelf") or ""
    entry = ShelfEntry.objects.filter(pk=sid, user=request.user).first() if sid.isdigit() else None
    initial = {"title": entry.title, "author": entry.author, "isbn": entry.isbn} if entry and request.method != "POST" else None
    form = BookForm(request.POST or None, request.FILES or None, default_city=_default_city(request.user), initial=initial)
    if request.method == "POST" and form.is_valid():
        book = form.save(commit=False)
        book.owner = request.user
        book._from_shelf = bool(entry)       # بدون ردیف قفسه، سیگنال خودش یکی می‌سازه
        book.save()
        form.save_extra_photos(book)
        if entry:
            entry.book = book
            entry.save(update_fields=["book", "updated_at"])
        notify_wishlists(book)
        check_badges(request.user)
        messages.success(request, "کتاب ثبت شد.")
        return redirect("books:detail", book.pk)
    return render(request, "books/form.html", {"form": form, "title": "قرار دادن برای معاوضه" if entry else "ثبت کتاب", "quality_weights": QUALITY_WEIGHTS, "shelf_entry": entry, **_cover_ctx()})


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
    return render(request, "books/form.html", {"form": form, "title": "ویرایش کتاب", "quality_weights": QUALITY_WEIGHTS, "existing_cover": bool(book.cover), **_cover_ctx()})


@login_required
@require_POST
def book_delete(request, pk):
    book = get_object_or_404(Book, pk=pk, owner=request.user)
    if book.status == Book.Status.RESERVED or book.exchanges.filter(status=Exchange.Status.REQUESTED).exists():
        messages.error(request, "تا درخواست‌های باز بسته نشدن نمی‌شه کتاب رو حذف کرد.")
        return redirect("books:detail", pk)
    book.soft_delete()          # تاریخچه‌ی مبادله، رأی و نقد می‌مونه؛ فقط از سایت پنهان می‌شه
    entry = book.shelf_entries.filter(user=request.user).first()
    book.shelf_entries.update(book=None)      # کتاب تو قفسه می‌مونه، فقط دیگه برای معاوضه نیست
    messages.success(request, "کتاب حذف شد.")
    if entry and request.POST.get("next") == "shelf":
        messages.success(request, "از معاوضه برداشته شد؛ تو قفسه‌ات هست.")
        return redirect("books:shelf_edit", entry.pk)
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
    books = list(request.user.books.select_related("city", "edition").prefetch_related("photos"))
    for book in books:
        book.quality = listing_quality(book)
    return render(request, "books/mine.html", {"books": books, "show_quality": True})


@login_required
def wishlist(request):
    if not settings.WISHLIST_ENABLED:
        return render(request, "books/wishlist.html", {"wishes": []})
    if request.method == "POST":
        wish, error = add_wish(request.user, request.POST.get("text", ""))
        if error:
            messages.error(request, error)
        else:
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


BULK_ROWS = 12      # اسکن پیوسته: ده کتاب پشت‌هم تو کمتر از دو دقیقه


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
    """استعلام شابک برای فرم ثبت کتاب: اطلاعات چاپ + تعداد منتظرها + هشدار کتاب تکراری."""
    raw = request.GET.get("isbn", "")
    error = isbn_lookup.isbn_error(raw)
    if error:
        return JsonResponse({"error": "invalid_isbn", "message": error}, status=400)
    isbn13 = isbn_lookup.normalize_isbn(raw)
    if not isbn13:
        return JsonResponse({"error": "not_found"}, status=404)
    edition = catalog.resolve(isbn13)
    if not edition:
        return JsonResponse({"error": "not_found", "isbn": isbn13}, status=404)
    user = request.user
    mine = Book.objects.filter(owner=user).filter(Q(isbn=isbn13) | Q(edition=edition)).count()
    elsewhere = Book.objects.filter(status=Book.Status.AVAILABLE).exclude(owner=user).filter(Q(isbn=isbn13) | Q(edition=edition)).count()
    return JsonResponse({
        "isbn": isbn13, "title": edition.title, "subtitle": edition.subtitle, "author": edition.author_line, "authors": edition.authors,
        "translators": edition.translators, "publisher": edition.publisher, "year": edition.year, "year_calendar": edition.year_calendar,
        "edition_no": edition.edition_no, "volume": edition.volume, "pages": edition.pages, "language": edition.language,
        "cover_url": edition.cover_url, "source": edition.source, "confidence": edition.confidence, "verified": edition.verified,
        "demand": demand_for(isbn13, edition.title, edition.author_line, exclude_user=user),
        "mine": mine, "available_elsewhere": elsewhere,
    })


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
    """
    کارت استوری. رندر Pillow سنگینه؛ بار اول رو دیسک (media/cards/<pk>-<نسخه>.png) ذخیره می‌شه و بعدش
    هیچ رندری نیست. پشت nginx با CARD_X_ACCEL_PREFIX خود nginx فایل رو می‌ده و gunicorn فقط هدر می‌فرسته.
    """
    from django.http import FileResponse
    from django.utils.http import quote_etag

    from common.throttle import client_ip, hit

    book = get_object_or_404(Book.objects.select_related("city"), pk=pk)
    path = book_card.cached_card_path(book)
    etag = quote_etag(path.stem.split("-", 1)[1])
    if request.META.get("HTTP_IF_NONE_MATCH") == etag and path.exists():
        return HttpResponse(status=304, headers={"ETag": etag})
    if not path.exists():
        if not hit("cardrender", client_ip(request), 20, 60):     # رندر نو فقط با سقف نرخ
            return HttpResponse("زیادی درخواست دادی؛ کمی بعد دوباره امتحان کن.", status=429)
        path = book_card.render_to_disk(book)
    prefix = getattr(settings, "CARD_X_ACCEL_PREFIX", "")
    if prefix:
        resp = HttpResponse(content_type="image/png")
        resp["X-Accel-Redirect"] = f"{prefix.rstrip('/')}/{path.name}"
    else:
        resp = FileResponse(open(path, "rb"), content_type="image/png")
    if request.GET.get("download"):
        resp["Content-Disposition"] = f'attachment; filename="hamvaraq-book-{book.pk}.png"'
    resp["Cache-Control"] = "public, max-age=300"
    resp["ETag"] = etag
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


def _cover_ctx():
    from . import covers

    return {"cover_designs": [(k, n, c) for k, n, c, *_ in covers.DESIGNS], "cover_categories": covers.CATEGORIES}


@login_required
@require_POST
def photo_move(request, pk):
    """جابه‌جایی عکس در آلبوم (جلو/عقب)؛ ترتیب از position موجود."""
    photo = get_object_or_404(BookPhoto.objects.select_related("book"), pk=pk, book__owner=request.user)
    photos = list(photo.book.photos.all())
    i = photos.index(photo)
    j = i - 1 if request.POST.get("dir") == "up" else i + 1
    if 0 <= j < len(photos):
        photos[i], photos[j] = photos[j], photos[i]
        for n, p in enumerate(photos):
            if p.position != n:
                p.position = n
                p.save(update_fields=["position"])
    return redirect("books:edit", photo.book_id)


@login_required
@require_POST
def photo_delete(request, pk):
    photo = get_object_or_404(BookPhoto.objects.select_related("book"), pk=pk, book__owner=request.user)
    book_pk = photo.book_id
    photo.image.delete(save=False)
    photo.delete()
    messages.success(request, "عکس حذف شد.")
    return redirect("books:edit", book_pk)


@throttle("quick", 90, 60, by="auto", methods=("GET",), json=True)
def quick_search(request):
    """نتیجه‌ی زنده‌ی پنجره‌ی جستجو: چند کتاب + چند معرفی‌نامه (عنوان/نویسنده/شابک، متن نرمال‌شده)."""
    ws = words(request.GET.get("q", ""))
    if not ws or sum(len(w) for w in ws) < 2:
        return JsonResponse({"books": [], "posts": [], "total": 0})
    qs = Book.objects.exclude(status=Book.Status.EXCHANGED)
    for w in ws:
        qs = qs.filter(search_text__contains=w)
    total = qs.count()
    books = [{
        "title": b.title, "author": b.author, "city": b.city.name if b.city_id else "",
        "thumb": b.thumb_url, "url": b.get_absolute_url(),
        "free": b.status == Book.Status.AVAILABLE,
    } for b in qs.select_related("city").order_by("-created_at")[:6]]
    from posts.models import Post
    pq = Post.objects.filter(status="published", published_at__lte=timezone.now())
    for w in ws:
        pq = pq.filter(search_text__contains=w)
    posts = [{"title": p.title, "by": p.author.username, "url": p.get_absolute_url()}
             for p in pq.select_related("author").order_by("-published_at")[:3]]
    return JsonResponse({"books": books, "posts": posts, "total": total})


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
        # از فهرست یکتای نویسنده‌ها (کش‌شده)؛ هر نویسنده فقط یه بار، با رایج‌ترین نوشتار و تعداد کتاب
        from .authors import known

        hits = [(n, d) for s, d, n in known("author") if all(w in s.replace("-", " ") for w in ws)]
        hits.sort(key=lambda t: -t[0])
        return JsonResponse({"items": [{"author": d, "count": n} for n, d in hits[:8]]})
    seen, items = set(), []
    # اول کاتالوگ (چاپ‌های ثبت‌شده با شابک و ناشر)، بعد آگهی‌های سایت
    from .models import Edition

    eq = Edition.objects.all()
    for w in ws:
        eq = eq.filter(title__icontains=w)
    for ed in eq.order_by("-confidence")[:8]:
        author = (ed.authors or [""])[0]
        if (ed.title, author) in seen:
            continue
        seen.add((ed.title, author))
        items.append({"title": ed.title, "author": author, "isbn": ed.isbn13 or "", "publisher": ed.publisher, "year": ed.year or ""})
    for title, author, isbn in qs.order_by("-created_at").values_list("title", "author", "isbn")[:60]:
        if (title, author) in seen:
            continue
        seen.add((title, author))
        items.append({"title": title, "author": author, "isbn": isbn})
        if len(items) == 8:
            break
    return JsonResponse({"items": items})


@throttle("coverpreview", 240, 60, by="auto", methods=("GET",))
def cover_preview(request, key):
    """پیش‌نمایش طرح جلد با عنوان/نویسنده‌ی تایپ‌شده؛ همون تابعی که فایل نهایی رو می‌سازه (کش یک‌روزه)."""
    import hashlib

    from django.core.cache import cache
    from django.http import Http404

    from . import covers

    if key not in covers.KEYS:
        raise Http404
    title = request.GET.get("t", "")[:120].strip() or "عنوان کتاب"
    author = request.GET.get("a", "")[:80].strip() or "نویسنده"
    ck = "cvp:" + hashlib.sha1(f"{key}|{title}|{author}".encode()).hexdigest()
    data = cache.get(ck)
    if data is None:
        data = covers.preview_png(key, title, author, 240)
        cache.set(ck, data, 86400)
    resp = HttpResponse(data, content_type="image/png")
    resp["Cache-Control"] = "public, max-age=86400"
    return resp
