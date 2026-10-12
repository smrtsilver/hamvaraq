from django.shortcuts import render
from django.utils import timezone

from .models import Challenge


def challenge_list(request):
    now = timezone.now()
    items = []
    for c in Challenge.objects.filter(is_active=True, ends_at__gte=now).order_by("ends_at"):
        done = c.progress(request.user) if request.user.is_authenticated else 0
        items.append({
            "c": c, "done": min(done, c.target), "percent": min(100, round(100 * done / c.target)) if c.target else 100,
            "upcoming": c.starts_at > now, "complete": done >= c.target,
        })
    return render(request, "challenges/list.html", {"items": items})
