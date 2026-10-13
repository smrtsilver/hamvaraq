"""
Content-Security-Policy با nonce. چون قالب‌ها دیگه style="" و onclick و javascript: ندارن، سیاست سخت‌گیرانه ممکنه.
پیش‌فرض Report-Only (CSP_ENFORCE=False) تا قبل از اجبار، تخلف‌ها تو لاگ `csp` دیده بشن؛ ادمین جنگو (inline زیاد داره) معاف است.
"""

import json
import logging
import secrets

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

log = logging.getLogger("csp")
EXEMPT_PREFIXES = ("/admin/",)


class CSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        if request.path.startswith(EXEMPT_PREFIXES) or "text/html" not in response.get("Content-Type", ""):
            return response
        policy = build_policy(request.csp_nonce)
        header = "Content-Security-Policy" if settings.CSP_ENFORCE else "Content-Security-Policy-Report-Only"
        response.setdefault(header, policy)
        return response


def build_policy(nonce):
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "manifest-src 'self'",
        "worker-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "report-uri /csp-report/",
    ])


def nonce_processor(request):
    return {"csp_nonce": getattr(request, "csp_nonce", "")}


@csrf_exempt
@require_POST
def report(request):
    """گزارش تخلف CSP مرورگر؛ فقط لاگ (بدنه‌ی کوتاه‌شده)."""
    try:
        data = json.loads(request.body[:4000] or b"{}")
        item = data.get("csp-report", data)
        log.warning("CSP violation: %s on %s", item.get("violated-directive") or item.get("effectiveDirective"), item.get("document-uri") or item.get("documentURL"))
    except ValueError:
        pass
    return HttpResponse(status=204)
