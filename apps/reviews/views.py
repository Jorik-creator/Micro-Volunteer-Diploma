"""
Views for the reviews app.

CreateReviewView — recipient leaves a review for the accepted volunteer
                   after the help request is marked as completed.
ReviewListView   — public list of reviews received by a specific user.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, ListView

from apps.accounts.models import User
from apps.requests.models import HelpRequest, Response

from .forms import ReviewForm
from .models import Review


# ---------------------------------------------------------------------------
# Create review (recipient only, after request is completed)
# ---------------------------------------------------------------------------


class CreateReviewView(LoginRequiredMixin, CreateView):
    """
    Recipient submits a review for the volunteer who completed their request.

    Permission rules (enforced in dispatch):
      - The help_request must have status='completed'.
      - The logged-in user must be the recipient of that request.
    """

    form_class = ReviewForm
    template_name = "reviews/review_form.html"

    def dispatch(self, request, *args, **kwargs):
        # Перевіряємо авторизацію до будь-якого DB-запиту
        # (щоб LoginRequiredMixin міг редиректити анонімних до /login/)
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # Resolve the help request early so it is available throughout the view
        self.help_request = get_object_or_404(HelpRequest, pk=self.kwargs["request_pk"])

        # Only completed requests can be reviewed
        if self.help_request.status != HelpRequest.Status.COMPLETED:
            raise PermissionDenied

        # Only the recipient of this request may leave a review
        if self.help_request.recipient != request.user:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Attach the author (current user / recipient)
        form.instance.author = self.request.user

        # Resolve the accepted volunteer for this request
        accepted_response = Response.objects.filter(
            help_request=self.help_request,
            status=Response.Status.ACCEPTED,
        ).first()

        # Guard: completed request may have no accepted volunteer (e.g. admin override)
        if accepted_response is None:
            messages.error(
                self.request,
                "Не знайдено підтвердженого волонтера для цього запиту.",
            )
            return redirect("requests:detail", pk=self.help_request.pk)

        form.instance.target = accepted_response.volunteer

        # Link the review to the help request
        form.instance.help_request = self.help_request

        try:
            # Savepoint — щоб IntegrityError не ламала зовнішню транзакцію
            with transaction.atomic():
                response = super().form_valid(form)
        except IntegrityError:
            # unique_together ['author', 'help_request'] — duplicate review attempt
            messages.error(
                self.request,
                "Ви вже залишили відгук для цього запиту.",
            )
            return redirect("requests:detail", pk=self.help_request.pk)

        messages.success(self.request, "Відгук успішно надіслано. Дякуємо!")
        return redirect("requests:detail", pk=self.help_request.pk)

    def get_success_url(self):
        # Fallback — form_valid always redirects explicitly, but a valid URL is required
        return reverse("requests:detail", kwargs={"pk": self.help_request.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["help_request"] = self.help_request
        return context


# ---------------------------------------------------------------------------
# Review list for a specific user (public, but login required)
# ---------------------------------------------------------------------------


class ReviewListView(LoginRequiredMixin, ListView):
    """
    Display all reviews received by a given user (identified by user_pk URL kwarg).
    """

    model = Review
    template_name = "reviews/review_list.html"
    context_object_name = "reviews"

    def get_queryset(self):
        # Filter reviews where the target matches the requested user pk
        return Review.objects.filter(target__pk=self.kwargs["user_pk"]).select_related(
            "author", "help_request"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Expose the reviewed user so templates can display their name/avatar
        context["target_user"] = get_object_or_404(User, pk=self.kwargs["user_pk"])
        return context
