import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from common import richtext
from common.text import words
from common.throttle import throttle

from . import services
from .forms import PostForm
from analytics.tracking import track

from .models import Post, Tag


def _published():
    return Post.objects.filter(status=Post.Status.PUBLISHED, published_at__lte=timezone.now()).select_related("author", "book", "category")


def post_list(request):
    qs = _published()
    q = request.GET.get("q", "").strip()
    for w in words(q):
        qs = qs.filter(search_text__contains=w)
    tag = request.GET.get("tag", "")
    if tag.isdigit():
        qs = qs.filter(tags__pk=int(tag))
    sort = request.GET.get("sort", "new")
    qs = qs.order_by("-is_featured", "-view_count", "-published_at") if sort == "popular" else qs.order_by("-is_featured", "-published_at")
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "posts/list.html", {
        "page": Paginator(qs.distinct(), 12).get_page(request.GET.get("page")), "q": q, "sort": sort, "qs": params.urlencode(),
        "tags": Tag.objects.filter(posts__status=Post.Status.PUBLISHED).distinct()[:30], "tag": tag,
    })


def post_detail(request, slug):
    post = get_object_or_404(Post.objects.select_related("author", "book__city", "category"), slug=slug)
    mine = request.user.is_authenticated and (post.author_id == request.user.pk or request.user.is_staff)
    if not post.is_published and not mine:
        raise Http404
    if post.is_published:
        track(request, "post", post, post.author_id)
    related = _published().exclude(pk=post.pk)
    related = (related.filter(book=post.book) if post.book_id else related.filter(tags__in=post.tags.all())).distinct()[:3]
    return render(request, "posts/detail.html", {
        "post": post, "tags": post.tags.all(), "related": related, "mine": mine, "ld_json": _post_ld(post, request),
        "more_by_author": _published().filter(author=post.author).exclude(pk=post.pk)[:3],
    })


def _post_ld(post, request):
    data = {
        "@context": "https://schema.org", "@type": "Article", "headline": post.title, "inLanguage": "fa",
        "author": {"@type": "Person", "name": post.author.username}, "mainEntityOfPage": request.build_absolute_uri(),
        "datePublished": (post.published_at or post.created_at).isoformat(), "dateModified": post.updated_at.isoformat(),
        "about": {"@type": "Book", "name": post.display_book_title, "author": {"@type": "Person", "name": post.display_book_author}},
    }
    if post.cover:
        data["image"] = request.build_absolute_uri(post.cover.url)
    if post.rating:
        data["@type"] = "Review"
        data["itemReviewed"] = data.pop("about")
        data["reviewRating"] = {"@type": "Rating", "ratingValue": post.rating, "bestRating": 5}
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


@login_required
@throttle("postsave", 12, 3600, by="user")
def post_create(request):
    since = timezone.now() - timedelta(days=1)
    if request.method == "POST" and Post.objects.filter(author=request.user, created_at__gte=since).count() >= _daily_limit():
        messages.error(request, "امروز به سقف تعداد نوشته رسیدی؛ فردا دوباره بنویس.")
        return redirect("posts:mine")
    initial = {"book": request.GET.get("book")} if request.GET.get("book", "").isdigit() else {}
    quote = request.GET.get("quote", "").strip()[:600]
    for key in ("book_title", "book_author"):
        if request.GET.get(key):
            initial[key] = request.GET[key][:150]
    if quote:
        # نقل‌قول از استوری‌ساز: همیشه با ارجاع به کتاب
        initial["body"] = "\n".join("> " + line for line in quote.splitlines() if line.strip()) + "\n\n"
        if initial.get("book_title"):
            initial["title"] = f"نقل‌قولی از «{initial['book_title']}»"[:140]
    form = PostForm(request.POST or None, request.FILES or None, user=request.user, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        form.save_m2m()
        post.set_tags_from_text(form.cleaned_data.get("tags_text", ""))
        services.submit(post)
        if post.status == Post.Status.PUBLISHED:
            messages.success(request, "معرفی‌ات منتشر شد. دست‌مریزاد!")
            return redirect(post)
        messages.success(request, "معرفی‌ات ثبت شد و بعد از تأیید مدیریت منتشر می‌شه. نوشته‌ی اولته؛ بعد از چند نوشته‌ی تأییدشده، مستقیم منتشر می‌شن.")
        return redirect("posts:mine")
    return render(request, "posts/form.html", {"form": form, "title": "معرفی یه کتاب"})


def _daily_limit():
    from django.conf import settings

    return settings.POST_DAILY_LIMIT


@login_required
@throttle("postsave", 20, 3600, by="user")
def post_edit(request, slug):
    post = get_object_or_404(Post, slug=slug)
    if post.author_id != request.user.pk:
        raise Http404
    form = PostForm(request.POST or None, request.FILES or None, instance=post, user=request.user)
    if request.method == "POST" and form.is_valid():
        post = form.save()
        # ویرایشِ نوشته‌ی منتشرشده‌ی نویسنده‌ی غیرمطمئن دوباره به صف می‌ره (جلوگیری از تغییر محتوا بعد از تأیید)
        if post.status in (Post.Status.PUBLISHED, Post.Status.REJECTED, Post.Status.DRAFT):
            services.submit(post)
        messages.success(request, "تغییرات ذخیره شد.")
        return redirect(post if post.status == Post.Status.PUBLISHED else "posts:mine")
    return render(request, "posts/form.html", {"form": form, "title": "ویرایش معرفی", "post": post})


@login_required
@require_POST
def post_delete(request, slug):
    post = get_object_or_404(Post, slug=slug)
    if post.author_id != request.user.pk and not request.user.is_staff:
        raise Http404
    post.delete()
    messages.success(request, "معرفی حذف شد.")
    return redirect("posts:mine")


@login_required
def my_posts(request):
    return render(request, "posts/mine.html", {"posts": request.user.posts.select_related("book")})


def author_posts(request, username):
    author = get_object_or_404(User, username=username)
    page = Paginator(_published().filter(author=author), 12).get_page(request.GET.get("page"))
    return render(request, "posts/author.html", {"author": author, "page": page, "qs": ""})


@login_required
@throttle("postpreview", 60, 600, by="user", json=True)
@require_POST
def preview(request):
    """پیش‌نمایش زنده‌ی ویرایشگر (همون رندر امنِ صفحه‌ی نوشته)."""
    return JsonResponse({"html": str(richtext.render(request.POST.get("body", "")))})
