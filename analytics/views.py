from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .tracking import record


@csrf_exempt          # امنیتش با توکن امضاشده‌ست؛ کوکی CSRF برای مهمان لازم نیست
@require_POST
def hit_view(request):
    token = request.POST.get("t", "")[:600]
    if token:
        record(request, token)
    return HttpResponse(status=204)
