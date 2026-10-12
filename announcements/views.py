import json
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from common.forms import PersianFormMixin
from common.location_forms import LocationMixin
from common.throttle import throttle

from . import ics, services
from .forms import AnnouncementForm
from analytics.tracking import track

from .models import Announcement, AnnouncementBookmark


class FilterForm(LocationMixin, PersianFormMixin, forms.Form):
    location_required = False
    province_only_ok = True
    location_empty = "همه"

    kind = forms.ChoiceField(choices=[("", "همه‌ی نوع‌ها"), *Announcement.Kind.choices], required=False, label="نوع")
    online = forms.BooleanField(required=False, label="فقط آنلاین")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_location(after="kind", province_ph="همه‌ی استان‌ها", city_ph="همه‌ی شهرها")

    def clean(self):
        cleaned = super().clean()
        city, province = cleaned.get("city"), cleaned.get("province")
        if city and province and city.province_id != province.pk:
            cleaned["city"] = None
            self.errors.pop("city", None)
        elif city and not province:
            cleaned["province"] = city.province
        return cleaned


def _published():
    return Announcement.objects.filter(status=Announcement.Status.PUBLISHED).select_related("city__province")


def _upcoming(qs, now=None):
    now = now or timezone.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    news = Q(kind=Announcement.Kind.NEWS, published_at__gte=now - timedelta(days=30))
    return qs.filter(news | Q(ends_at__gte=now) | Q(ends_at__isnull=True, starts_at__gte=today))


def announcement_list(request):
    tab = "past" if request.GET.get("tab") == "past" else "upcoming"
    form = FilterForm(request.GET)
    qs = _published()
    if form.is_valid():
        d = form.cleaned_data
        if d["kind"]:
            qs = qs.filter(kind=d["kind"])
        if d["online"]:
            qs = qs.filter(is_online=True)
        if d["city"]:
            qs = qs.filter(city=d["city"])
        elif d["province"]:
            qs = qs.filter(city__province=d["province"])
    upcoming = _upcoming(qs)
    when = Coalesce("starts_at", "published_at")
    if tab == "upcoming":
        qs = upcoming.order_by("-is_featured", when)
    else:
        qs = qs.exclude(pk__in=upcoming.values("pk")).order_by(when.desc())
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("tab", None)
    return render(request, "announcements/list.html", {
        "form": form, "tab": tab, "page": Paginator(qs, 12).get_page(request.GET.get("page")), "qs": params.urlencode() + ("&" if params else "") + f"tab={tab}",
        "base_qs": params.urlencode(), "now": timezone.now(),
    })


def announcement_detail(request, pk, slug=None):
    item = get_object_or_404(Announcement.objects.select_related("city__province", "submitted_by"), pk=pk)
    mine = request.user.is_authenticated and (item.submitted_by_id == request.user.pk or request.user.is_staff)
    if item.status != Announcement.Status.PUBLISHED and not mine:
        raise Http404
    if item.status == Announcement.Status.PUBLISHED:
        track(request, "event", item, item.submitted_by_id)
    return render(request, "announcements/detail.html", {
        "item": item, "mine": mine, "ld_json": _event_ld(item, request),
        "bookmarked": request.user.is_authenticated and item.bookmarks.filter(user=request.user).exists(),
        "can_ics": bool(item.starts_at),
    })


def _event_ld(item, request):
    if item.is_news or not item.starts_at:
        data = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": item.title, "datePublished": (item.published_at or item.created_at).isoformat(),
                "description": item.summary, "inLanguage": "fa"}
    else:
        data = {"@context": "https://schema.org", "@type": "Event", "name": item.title, "description": item.summary, "startDate": item.starts_at.isoformat(),
                "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode" if item.is_online else "https://schema.org/OfflineEventAttendanceMode",
                "eventStatus": "https://schema.org/EventScheduled", "inLanguage": "fa", "isAccessibleForFree": item.is_free}
        if item.ends_at:
            data["endDate"] = item.ends_at.isoformat()
        data["location"] = ({"@type": "VirtualLocation", "url": item.link or request.build_absolute_uri()} if item.is_online else
                            {"@type": "Place", "name": item.venue or (item.city.name if item.city_id else ""), "address": item.address or (item.city.name if item.city_id else "")})
        if item.organizer:
            data["organizer"] = {"@type": "Organization", "name": item.organizer}
    if item.cover:
        data["image"] = request.build_absolute_uri(item.cover.url)
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def announcement_ics(request, pk):
    item = get_object_or_404(Announcement, pk=pk, status=Announcement.Status.PUBLISHED)
    if not item.starts_at:
        raise Http404
    body = ics.build(item, request.build_absolute_uri(item.get_absolute_url()))
    resp = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="hamvaraq-event-{item.pk}.ics"'
    return resp


@login_required
@require_POST
def toggle_bookmark(request, pk):
    item = get_object_or_404(Announcement, pk=pk, status=Announcement.Status.PUBLISHED)
    deleted, _ = AnnouncementBookmark.objects.filter(user=request.user, announcement=item).delete()
    if deleted:
        messages.info(request, "یادآوری برداشته شد.")
    else:
        AnnouncementBookmark.objects.create(user=request.user, announcement=item)
        messages.success(request, "قبل از شروع بهت خبر می‌دیم.")
    return redirect(item)


@login_required
@throttle("announce", 10, 3600, by="user")
def announcement_create(request):
    since = timezone.now() - timedelta(days=1)
    if request.method == "POST" and not request.user.is_staff and \
            Announcement.objects.filter(submitted_by=request.user, created_at__gte=since).count() >= settings.ANNOUNCEMENT_DAILY_LIMIT:
        messages.error(request, "امروز به سقف تعداد اطلاعیه رسیدی؛ فردا دوباره امتحان کن.")
        return redirect("announcements:mine")
    form = AnnouncementForm(request.POST or None, request.FILES or None, initial={"city": request.user.city_id})
    if request.method == "POST" and form.is_valid():
        item = services.submit(form.save(commit=False), request.user)
        if item.status == Announcement.Status.PUBLISHED:
            messages.success(request, "اطلاعیه منتشر شد.")
            return redirect(item)
        messages.success(request, "اطلاعیه‌ات ثبت شد و بعد از تأیید مدیریت منتشر می‌شه.")
        return redirect("announcements:mine")
    return render(request, "announcements/form.html", {"form": form, "title": "ثبت اطلاعیه"})


@login_required
def announcement_edit(request, pk):
    item = get_object_or_404(Announcement, pk=pk)
    if item.submitted_by_id != request.user.pk or item.status == Announcement.Status.PUBLISHED and not request.user.is_staff:
        raise Http404
    form = AnnouncementForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == "POST" and form.is_valid():
        item = services.submit(form.save(commit=False), request.user)
        messages.success(request, "تغییرات ذخیره شد و برای تأیید دوباره ارسال شد.")
        return redirect("announcements:mine")
    return render(request, "announcements/form.html", {"form": form, "title": "ویرایش اطلاعیه", "item": item})


@login_required
def my_announcements(request):
    return render(request, "announcements/mine.html", {"items": request.user.announcements.select_related("city")})
