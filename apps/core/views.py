import hmac
from datetime import date

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .tasks import run_periodic_tasks


@csrf_exempt
@require_POST
def run_tasks(request):
    """Cron entry point, authorised by a shared secret in the Authorization header."""
    secret = settings.CRON_SECRET
    if not secret:
        raise Http404
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), secret.encode()):
        return JsonResponse({"error": "unauthorized"}, status=401)
    return JsonResponse(run_periodic_tasks())


POLICY_UPDATED = date(2026, 9, 24)


def privacy(request):
    return render(request, "core/privacy.html", {"updated": POLICY_UPDATED})


def rules(request):
    return render(request, "core/rules.html")
