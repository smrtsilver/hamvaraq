from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

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
    owner = get_object_or_404(User, username=username)
    shelf = owner.books.exclude(status=Book.Status.RESERVED).select_related("city").order_by("-created_at")
    return render(request, "accounts/profile.html", {
        "owner": owner,
        "books": shelf,
        "badges": owner.user_badges.select_related("badge"),
    })


@login_required
def settings_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تنظیمات ذخیره شد.")
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {"form": form})
