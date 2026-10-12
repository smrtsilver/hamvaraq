import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from common.throttle import throttle

from . import push
from .forms import PreferenceForm
from .models import NotificationPreference, PushSubscription

MAX_DEVICES = 10


@login_required
def notification_list(request):
    items = list(request.user.notifications.all()[:100])
    # لیست رو که دید، همه خونده‌شده حساب می‌شن (ولی هنوز تو همین صفحه برجسته‌ان)
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "notifications/list.html", {"items": items})


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("notifications:list")


@login_required
def notification_settings(request):
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
    form = PreferenceForm(request.POST or None, instance=prefs)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "ترجیحات اعلان ذخیره شد.")
        return redirect("notifications:settings")
    return render(request, "notifications/settings.html", {
        "form": form, "push_enabled": push.configured(), "vapid_key": settings.VAPID_PUBLIC_KEY,
        "devices": request.user.push_subscriptions.count(),
    })


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return None


@login_required
@throttle("pushsub", 30, 3600, by="user", json=True)
@require_POST
def push_subscribe(request):
    data = _json_body(request)
    keys = (data or {}).get("keys") or {}
    endpoint, p256dh, auth = (data or {}).get("endpoint", ""), keys.get("p256dh", ""), keys.get("auth", "")
    if not push.configured():
        return JsonResponse({"error": "not_configured"}, status=503)
    if not (endpoint.startswith("https://") and len(endpoint) <= 700 and p256dh and auth and len(p256dh) <= 200 and len(auth) <= 100):
        return JsonResponse({"error": "invalid"}, status=400)
    existing = PushSubscription.objects.filter(endpoint=endpoint).first()
    if not existing and request.user.push_subscriptions.count() >= MAX_DEVICES:
        return JsonResponse({"error": "too_many"}, status=400)
    PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={
        "user": request.user, "p256dh": p256dh, "auth": auth, "failures": 0,
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:200]})
    return JsonResponse({"ok": True, "devices": request.user.push_subscriptions.count()})


@login_required
@require_POST
def push_unsubscribe(request):
    data = _json_body(request) or {}
    PushSubscription.objects.filter(user=request.user, endpoint=data.get("endpoint", "")).delete()
    return JsonResponse({"ok": True, "devices": request.user.push_subscriptions.count()})


@login_required
@throttle("pushtest", 5, 3600, by="user", json=True)
@require_POST
def push_test(request):
    if not push.configured():
        return JsonResponse({"error": "not_configured"}, status=503)
    sent = push.send_payload(request.user.pk, {
        "title": "هم‌ورق", "body": "اعلان آزمایشی؛ همه‌چیز درسته ✅", "url": "/notifications/settings/", "tag": "test",
        "icon": "/static/brand/icon-192.png", "badge": "/static/brand/favicon-48.png"})
    return JsonResponse({"ok": True, "sent": sent})
