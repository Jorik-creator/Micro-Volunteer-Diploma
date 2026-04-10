"""
Views for the stats app.

Staff-only dashboard with platform-wide statistics:
  StatsView   — TemplateView rendering Chart.js dashboard (staff only, 403 for others)
  stats_data  — JSON endpoint for dynamic chart data (staff only, FBV)
"""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count
from django.http import HttpResponseForbidden, JsonResponse
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.requests.models import HelpRequest
from apps.reviews.models import Review


# ---------------------------------------------------------------------------
# Staff dashboard (CBV)
# ---------------------------------------------------------------------------


class StatsView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Platform statistics dashboard — staff only.

    Returns 403 (not redirect) for authenticated non-staff users via
    raise_exception = True. LoginRequiredMixin is first in MRO so
    unauthenticated users are redirected to login before the staff check runs.
    """

    template_name = "stats/dashboard.html"

    def test_func(self):
        """Allow access only to staff members."""
        return self.request.user.is_staff

    def handle_no_permission(self):
        """
        Анонімні користувачі → редирект на /login/.
        Авторизовані не-staff → 403 Forbidden.
        """
        if not self.request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(self.request.get_full_path())
        raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # --- Aggregate counts ---
        context["total_requests"] = HelpRequest.objects.count()
        context["total_reviews"] = Review.objects.count()

        # --- Average rating (None when no reviews exist → fall back to 0) ---
        avg_result = Review.objects.aggregate(avg=Avg("rating"))["avg"]
        context["avg_rating"] = avg_result if avg_result is not None else 0

        # --- Requests grouped by status ---
        # QuerySet: [{"status": "active", "count": N}, ...]
        status_qs = HelpRequest.objects.values("status").annotate(count=Count("id"))
        requests_by_status = {row["status"]: row["count"] for row in status_qs}
        context["requests_by_status"] = requests_by_status

        # --- Requests grouped by category name ---
        # category__name is None when category was deleted (SET_NULL)
        category_qs = HelpRequest.objects.values("category__name").annotate(
            count=Count("id")
        )
        requests_by_category = {
            (row["category__name"] or "Без категорії"): row["count"]
            for row in category_qs
        }
        context["requests_by_category"] = requests_by_category

        # --- Top 5 volunteers by number of reviews received ---
        context["top_volunteers"] = User.objects.annotate(
            review_count=Count("reviews_received")
        ).order_by("-review_count")[:5]

        # --- Chart.js data: statuses ---
        # Preserve the canonical Status order for consistent chart rendering
        status_order = [choice[0] for choice in HelpRequest.Status.choices]
        context["status_labels"] = [HelpRequest.Status(s).label for s in status_order]
        context["status_data"] = [requests_by_status.get(s, 0) for s in status_order]

        # --- Chart.js data: categories ---
        context["category_labels"] = list(requests_by_category.keys())
        context["category_data"] = list(requests_by_category.values())

        return context


# ---------------------------------------------------------------------------
# JSON endpoint for dynamic chart refresh (FBV)
# ---------------------------------------------------------------------------


@login_required
def stats_data(request):
    """
    Return platform statistics as JSON for Chart.js AJAX refresh.

    Staff-only: returns 403 for authenticated non-staff users.
    Response shape:
      {
        "statuses": {"active": N, "in_progress": N, ...},
        "categories": {"category_name": count, ...},
        "avg_rating": float | null
      }
    """
    if not request.user.is_staff:
        return HttpResponseForbidden()

    # Build status counts for every canonical status value
    status_qs = HelpRequest.objects.values("status").annotate(count=Count("id"))
    status_map = {row["status"]: row["count"] for row in status_qs}

    # Ensure all Status choices are present in the response (even if count is 0)
    statuses = {
        choice[0]: status_map.get(choice[0], 0) for choice in HelpRequest.Status.choices
    }

    # Category counts (null category → "Без категорії")
    category_qs = HelpRequest.objects.values("category__name").annotate(
        count=Count("id")
    )
    categories = {
        (row["category__name"] or "Без категорії"): row["count"] for row in category_qs
    }

    # Average rating — return null (None → JSON null) when no reviews exist
    avg_result = Review.objects.aggregate(avg=Avg("rating"))["avg"]
    avg_rating = float(round(avg_result, 2)) if avg_result is not None else None

    return JsonResponse(
        {
            "statuses": statuses,
            "categories": categories,
            "avg_rating": avg_rating,
        }
    )
