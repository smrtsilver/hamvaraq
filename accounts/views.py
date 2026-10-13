from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from books.models import Book

from common.throttle import throttle

from .badges import grant_welcome
from .forms import ProfileForm, SignupForm
from .ip import ip_key
from .models import User


@throttle("signup", 10, 3600, by="ip")
def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        key = ip_key(request)
        user.signup_ip_hash = user.last_ip_hash = key
        user.save(update_fields=["signup_ip_hash", "last_ip_hash"])
        given = grant_welcome(user, key)
        login(request, user)
        if given:
            messages.success(request, f"خوش اومدی! {given} امتیاز هدیه گرفتی؛ می‌تونی همین الان یه کتاب بگیری.")
            return redirect("books:list")
        messages.success(request, "خوش اومدی! با ثبت و واگذاری اولین کتابت امتیاز می‌گیری.")
        return redirect("books:create")
    return render(request, "accounts/signup.html", {"form": form})


def profile(request, username):
    from exchanges.models import Exchange

    owner = get_object_or_404(User.objects.select_related("city__province"), username=username, deleted_at__isnull=True)
    shelf_qs = owner.shelf.all()
    shelf = list(shelf_qs.select_related("book").order_by("-created_at")[:120])
    available = list(owner.books.filter(status=Book.Status.AVAILABLE).select_related("city__province").order_by("-created_at")[:24])
    done = Exchange.objects.filter(status=Exchange.Status.COMPLETED)
    return render(request, "accounts/profile.html", {
        "owner": owner,
        "books": shelf,
        "shelf_count": shelf_qs.count() if len(shelf) == 120 else len(shelf),
        "available": available,
        "given": done.filter(owner=owner).count(),
        "received": done.filter(requester=owner).count(),
        "badges": owner.user_badges.select_related("badge"),
        "followers": owner.follower_set.count(), "following": owner.following_set.count(),
        "is_following": request.user.is_authenticated and owner.follower_set.filter(follower=request.user).exists(),
        "goal": _public_goal(owner),
        "highlights": owner.highlights.filter(is_public=True)[:6],
    })


def _public_goal(owner):
    from books.reading import goal_progress

    return goal_progress(owner)


@login_required
@require_POST
@throttle("follow", 120, 3600, by="user")
def follow_toggle(request, username):
    from .models import Follow

    target = get_object_or_404(User, username=username, deleted_at__isnull=True, is_active=True)
    if target != request.user:
        f, created = Follow.objects.get_or_create(follower=request.user, followee=target)
        if not created:
            f.delete()
    return redirect("accounts:profile", username)


@login_required
def feed(request):
    from . import feed as feedmod

    return render(request, "accounts/feed.html", {"items": feedmod.build(request.user), "suggested": feedmod.suggested_readers(request.user)})


@login_required
def settings_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تنظیمات ذخیره شد.")
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {"form": form})


@login_required
def my_points(request):
    """تاریخچه‌ی امتیاز: هر تغییر با دلیل و موجودی بعدش."""
    from django.core.paginator import Paginator

    entries = request.user.point_entries.select_related("exchange__book")
    page = Paginator(entries, 30).get_page(request.GET.get("page"))
    return render(request, "accounts/points.html", {"page": page, "qs": ""})


@login_required
def my_stats(request):
    from analytics.services import user_stats

    return render(request, "accounts/stats.html", {"s": user_stats(request.user)})


@login_required
@throttle("account_delete", 5, 3600, by="user")
def delete_account(request):
    """حذف حساب = ناشناس‌سازی (تأیید با رمز)؛ تاریخچه‌ی مبادله‌ی دیگران دست‌نخورده می‌مونه."""
    from django.contrib.auth import logout

    from .services import AccountError, anonymize_user

    if request.method == "POST":
        if not request.user.check_password(request.POST.get("password", "")):
            messages.error(request, "رمز اشتباهه.")
        else:
            try:
                anonymize_user(request.user)
            except AccountError as e:
                messages.error(request, str(e))
            else:
                logout(request)
                messages.success(request, "حساب تو حذف شد. ممنون که با هم‌ورق بودی.")
                return redirect("home")
    return render(request, "accounts/delete.html")
