from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from common.throttle import throttle

from .forms import ClubForm, ClubPostForm
from .models import Club, ClubMember, ClubPost

MAX_OWNED = 5


def club_list(request):
    qs = Club.objects.filter(is_active=True).select_related("city", "owner").annotate(n=Count("members"))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(current_title__icontains=q) | Q(city__name__icontains=q))
    mine = set(request.user.club_memberships.values_list("club_id", flat=True)) if request.user.is_authenticated else set()
    page = Paginator(qs.order_by("-n", "-created_at"), 18).get_page(request.GET.get("page"))
    return render(request, "clubs/list.html", {"page": page, "mine": mine, "q": q})


def club_detail(request, slug):
    from announcements.views import _published, _upcoming

    club = get_object_or_404(Club.objects.select_related("owner", "city"), slug=slug, is_active=True)
    is_member = request.user.is_authenticated and club.members.filter(user=request.user).exists()
    form = ClubPostForm(request.POST or None) if is_member else None
    if request.method == "POST" and form is not None and form.is_valid():
        if ClubPost.objects.filter(user=request.user, club=club).count() and _too_fast(request.user, club):
            messages.error(request, "کمی صبر کن و بعد بنویس.")
        else:
            ClubPost.objects.create(club=club, user=request.user, text=form.cleaned_data["text"])
        return redirect(club)
    posts = club.posts.select_related("user")[:40]
    members = club.members.select_related("user").order_by("joined_at")[:24]
    events = list(_upcoming(_published()).filter(club=club)[:5])
    return render(request, "clubs/detail.html", {"club": club, "is_member": is_member, "form": form, "posts": posts,
                                                 "members": members, "member_n": club.members.count(), "events": events,
                                                 "is_owner": request.user == club.owner})


def _too_fast(user, club):
    from datetime import timedelta

    from django.utils import timezone

    return ClubPost.objects.filter(user=user, club=club, created_at__gte=timezone.now() - timedelta(seconds=20)).exists()


@login_required
@throttle("clubcreate", 5, 86400, by="user")
def club_create(request):
    form = ClubForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if Club.objects.filter(owner=request.user, is_active=True).count() >= MAX_OWNED:
            messages.error(request, f"حداکثر {MAX_OWNED} باشگاه فعال می‌تونی داشته باشی.")
            return redirect("clubs:list")
        club = form.save(commit=False)
        club.owner = request.user
        club.save()
        ClubMember.objects.create(club=club, user=request.user)
        messages.success(request, "باشگاهت ساخته شد. دوستانت رو دعوت کن!")
        return redirect(club)
    return render(request, "clubs/form.html", {"form": form, "title": "ساخت باشگاه کتاب"})


@login_required
def club_edit(request, slug):
    club = get_object_or_404(Club, slug=slug, owner=request.user)
    form = ClubForm(request.POST or None, instance=club)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "ذخیره شد.")
        return redirect(club)
    return render(request, "clubs/form.html", {"form": form, "title": "ویرایش باشگاه", "club": club})


@login_required
@require_POST
@throttle("clubjoin", 60, 3600, by="user")
def club_join(request, slug):
    club = get_object_or_404(Club, slug=slug, is_active=True)
    m, created = ClubMember.objects.get_or_create(club=club, user=request.user)
    if not created and club.owner_id != request.user.pk:
        m.delete()
        messages.success(request, "از باشگاه بیرون اومدی.")
    elif created:
        messages.success(request, f"به «{club.name}» خوش اومدی!")
    return redirect(club)


@login_required
@require_POST
def post_delete(request, pk):
    p = get_object_or_404(ClubPost.objects.select_related("club"), pk=pk)
    if request.user.pk in (p.user_id, p.club.owner_id) or request.user.is_staff:
        p.delete()
    return redirect(p.club)
