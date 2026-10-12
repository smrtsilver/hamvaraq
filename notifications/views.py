from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


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
