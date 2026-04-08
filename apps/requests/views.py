"""
Views for the requests app.

Public / volunteer views:
  HelpRequestListView   — list of active requests with filters
  HelpRequestDetailView — request details (role-aware)
  MapView               — Leaflet map page
  map_data              — JSON endpoint for map markers
  respond_to_request    — volunteer submits a response

Recipient views:
  HelpRequestCreateView — create a new request
  HelpRequestUpdateView — edit an active request
  MyRequestsView        — recipient's own requests
  cancel_request        — cancel active / in_progress request

Recipient action views:
  accept_volunteer  — accept a pending response
  reject_volunteer  — reject a pending response

Volunteer action views:
  complete_request  — mark request as completed (accepted volunteer only)
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from apps.accounts.decorators import recipient_required, volunteer_required
from .forms import FilterForm, HelpRequestForm, ResponseForm
from .models import HelpRequest, Response
from .utils import offset_coordinates

MAX_ACTIVE_REQUESTS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _urgency_color(urgency: str) -> str:
    return {
        "low": "success",
        "medium": "warning",
        "high": "orange",
        "critical": "danger",
    }.get(urgency, "secondary")


# ---------------------------------------------------------------------------
# List & Map views (authenticated users)
# ---------------------------------------------------------------------------


class HelpRequestListView(LoginRequiredMixin, ListView):
    """Paginated list of active help requests with optional filters."""

    model = HelpRequest
    template_name = "requests/request_list.html"
    context_object_name = "requests"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            HelpRequest.objects.filter(
                status=HelpRequest.Status.ACTIVE,
            )
            .select_related("recipient", "category")
            .order_by(
                # Critical first, then by date
                "urgency",
                "needed_date",
            )
        )
        form = FilterForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get("category"):
                qs = qs.filter(category=form.cleaned_data["category"])
            if form.cleaned_data.get("urgency"):
                qs = qs.filter(urgency=form.cleaned_data["urgency"])
            if form.cleaned_data.get("duration"):
                qs = qs.filter(duration=form.cleaned_data["duration"])
            if form.cleaned_data.get("date_from"):
                qs = qs.filter(needed_date__date__gte=form.cleaned_data["date_from"])
            if form.cleaned_data.get("date_to"):
                qs = qs.filter(needed_date__date__lte=form.cleaned_data["date_to"])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = FilterForm(self.request.GET)
        return context


class MapView(LoginRequiredMixin, TemplateView):
    """Leaflet map page — data loaded via AJAX from map_data endpoint."""

    template_name = "requests/map.html"


@login_required
def map_data(request):
    """Return active requests as JSON for Leaflet map markers."""
    active = HelpRequest.objects.filter(
        status=HelpRequest.Status.ACTIVE,
    ).select_related("category")

    data = []
    for hr in active:
        if hr.latitude and hr.longitude:
            # Offset coordinates for privacy
            lat, lon = offset_coordinates(hr.latitude, hr.longitude, offset_meters=150)
        else:
            continue

        data.append(
            {
                "id": hr.pk,
                "title": hr.title,
                "urgency": hr.urgency,
                "urgency_display": hr.get_urgency_display(),
                "category": hr.category.name if hr.category else "",
                "address": hr.address,
                "needed_date": hr.needed_date.strftime("%d.%m.%Y %H:%M"),
                "duration": hr.get_duration_display(),
                "lat": lat,
                "lon": lon,
                "url": f"/requests/{hr.pk}/",
            }
        )

    return JsonResponse(data, safe=False)


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class HelpRequestDetailView(LoginRequiredMixin, DetailView):
    """
    Show full request details.
    Recipients see their own responses list.
    Volunteers see a respond button (if they haven't yet).
    """

    model = HelpRequest
    template_name = "requests/request_detail.html"
    context_object_name = "help_request"

    def get_queryset(self):
        return HelpRequest.objects.select_related("recipient", "category")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hr = self.object
        user = self.request.user

        context["response_form"] = ResponseForm()
        context["urgency_color"] = _urgency_color(hr.urgency)

        # Count accepted responses
        context["accepted_count"] = hr.responses.filter(
            status=Response.Status.ACCEPTED
        ).count()

        if user.is_recipient and hr.recipient == user:
            # Recipient sees all responses
            context["responses"] = hr.responses.select_related("volunteer").order_by(
                "status", "-created_at"
            )
            context["is_owner"] = True
        elif user.is_volunteer:
            context["is_owner"] = False
            # Check if this volunteer already responded
            context["user_response"] = hr.responses.filter(volunteer=user).first()
            # After acceptance — show exact address and recipient phone
            accepted_response = hr.responses.filter(
                volunteer=user, status=Response.Status.ACCEPTED
            ).first()
            context["is_accepted"] = accepted_response is not None
        else:
            context["is_owner"] = False
            context["user_response"] = None
            context["is_accepted"] = False

        return context


# ---------------------------------------------------------------------------
# Create / Update (recipients only)
# ---------------------------------------------------------------------------


class HelpRequestCreateView(LoginRequiredMixin, CreateView):
    """Create a new help request. Only recipients allowed, max 10 active."""

    model = HelpRequest
    form_class = HelpRequestForm
    template_name = "requests/request_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if not request.user.is_recipient:
            messages.error(
                request, "Ця сторінка доступна тільки для отримувачів допомоги."
            )
            return redirect("home")
        # Max active requests guard
        active_count = HelpRequest.objects.filter(
            recipient=request.user,
            status=HelpRequest.Status.ACTIVE,
        ).count()
        if active_count >= MAX_ACTIVE_REQUESTS:
            messages.error(
                request,
                f"Досягнуто максимум активних запитів ({MAX_ACTIVE_REQUESTS}). "
                "Завершіть або скасуйте деякі перед створенням нового.",
            )
            return redirect("requests:my-requests")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.recipient = self.request.user
        messages.success(self.request, "Запит успішно створено!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("requests:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Створити запит допомоги"
        context["submit_label"] = "Створити запит"
        return context


class HelpRequestUpdateView(LoginRequiredMixin, UpdateView):
    """Edit an active help request. Owner + active status required."""

    model = HelpRequest
    form_class = HelpRequestForm
    template_name = "requests/request_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        obj = self.get_object()
        if obj.recipient != request.user:
            messages.error(request, "У вас немає доступу до цього запиту.")
            return redirect("home")
        if obj.status not in [HelpRequest.Status.ACTIVE]:
            messages.error(request, "Редагування недоступне для цього статусу запиту.")
            return redirect("requests:detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Запит оновлено.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("requests:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Редагувати запит"
        context["submit_label"] = "Зберегти зміни"
        return context


# ---------------------------------------------------------------------------
# My requests (recipient dashboard)
# ---------------------------------------------------------------------------


class MyRequestsView(LoginRequiredMixin, ListView):
    """Recipient sees all their own requests with status history."""

    template_name = "requests/my_requests.html"
    context_object_name = "requests"
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if not request.user.is_recipient:
            messages.error(
                request, "Ця сторінка доступна тільки для отримувачів допомоги."
            )
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            HelpRequest.objects.filter(
                recipient=self.request.user,
            )
            .select_related("category")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context["active_count"] = qs.filter(status=HelpRequest.Status.ACTIVE).count()
        context["in_progress_count"] = qs.filter(
            status=HelpRequest.Status.IN_PROGRESS
        ).count()
        context["completed_count"] = qs.filter(
            status=HelpRequest.Status.COMPLETED
        ).count()
        return context


# ---------------------------------------------------------------------------
# Respond to request (volunteer)
# ---------------------------------------------------------------------------


@volunteer_required
def respond_to_request(request, pk):
    """Volunteer submits a response to an active request."""
    help_request = get_object_or_404(
        HelpRequest, pk=pk, status=HelpRequest.Status.ACTIVE
    )

    # Prevent author from responding to own request (safety check)
    if help_request.recipient == request.user:
        messages.error(request, "Ви не можете відгукнутись на власний запит.")
        return redirect("requests:detail", pk=pk)

    # Prevent duplicate responses (view-level check before DB constraint fires)
    if Response.objects.filter(
        volunteer=request.user, help_request=help_request
    ).exists():
        messages.warning(request, "Ви вже відгукнулись на цей запит.")
        return redirect("requests:detail", pk=pk)

    if request.method == "POST":
        form = ResponseForm(request.POST)
        if form.is_valid():
            response = form.save(commit=False)
            response.help_request = help_request
            response.volunteer = request.user
            response.save()
            messages.success(request, "Ваш відгук надіслано! Очікуйте підтвердження.")
            return redirect("requests:detail", pk=pk)
    else:
        form = ResponseForm()

    # On GET or invalid POST — redirect back (form is on detail page)
    return redirect("requests:detail", pk=pk)


# ---------------------------------------------------------------------------
# Accept / Reject volunteer (recipient)
# ---------------------------------------------------------------------------


@recipient_required
def accept_volunteer(request, response_id):
    """
    Recipient accepts a pending volunteer response.
    If accepted_count reaches volunteers_needed → request moves to in_progress
    and all remaining pending responses are auto-rejected.
    Uses select_for_update to prevent race conditions.
    """
    if request.method != "POST":
        return redirect("home")

    response = get_object_or_404(
        Response,
        pk=response_id,
        help_request__recipient=request.user,
        status=Response.Status.PENDING,
    )

    with transaction.atomic():
        hr = HelpRequest.objects.select_for_update().get(
            pk=response.help_request_id,
            status=HelpRequest.Status.ACTIVE,
        )
        response.status = Response.Status.ACCEPTED
        response.save()

        accepted_count = Response.objects.filter(
            help_request=hr,
            status=Response.Status.ACCEPTED,
        ).count()

        if accepted_count >= hr.volunteers_needed:
            hr.status = HelpRequest.Status.IN_PROGRESS
            hr.save()
            # Auto-reject all remaining pending responses
            Response.objects.filter(
                help_request=hr,
                status=Response.Status.PENDING,
            ).update(status=Response.Status.REJECTED)
            messages.success(
                request,
                f'Набрано {accepted_count} волонтер(ів). Запит перейшов у статус "В процесі".',
            )
        else:
            messages.success(
                request,
                f"Волонтера підтверджено ({accepted_count}/{hr.volunteers_needed}).",
            )

    return redirect("requests:detail", pk=response.help_request_id)


@recipient_required
def reject_volunteer(request, response_id):
    """Recipient rejects a pending volunteer response."""
    if request.method != "POST":
        return redirect("home")

    response = get_object_or_404(
        Response,
        pk=response_id,
        help_request__recipient=request.user,
        status=Response.Status.PENDING,
    )
    response.status = Response.Status.REJECTED
    response.save()
    messages.info(request, "Відгук волонтера відхилено.")
    return redirect("requests:detail", pk=response.help_request_id)


# ---------------------------------------------------------------------------
# Complete request (accepted volunteer)
# ---------------------------------------------------------------------------


@login_required
def complete_request(request, pk):
    """
    Only an accepted volunteer can mark the request as completed.
    Spec: Q23 — volunteer, not recipient, closes the request.
    """
    if request.method != "POST":
        return redirect("requests:detail", pk=pk)

    help_request = get_object_or_404(
        HelpRequest, pk=pk, status=HelpRequest.Status.IN_PROGRESS
    )

    is_accepted_volunteer = Response.objects.filter(
        help_request=help_request,
        volunteer=request.user,
        status=Response.Status.ACCEPTED,
    ).exists()

    if not is_accepted_volunteer:
        messages.error(request, "Тільки підтверджений волонтер може завершити запит.")
        return redirect("requests:detail", pk=pk)

    help_request.status = HelpRequest.Status.COMPLETED
    help_request.save()
    messages.success(request, "Запит позначено як виконаний. Дякуємо за допомогу!")
    return redirect("requests:detail", pk=pk)


# ---------------------------------------------------------------------------
# Cancel request (recipient)
# ---------------------------------------------------------------------------


@recipient_required
def cancel_request(request, pk):
    """
    Recipient cancels an active or in_progress request.
    Spec: Q24 — accepted/pending volunteers stay in archive; senders get info.
    """
    if request.method != "POST":
        return redirect("requests:detail", pk=pk)

    help_request = get_object_or_404(HelpRequest, pk=pk, recipient=request.user)

    if help_request.status not in [
        HelpRequest.Status.ACTIVE,
        HelpRequest.Status.IN_PROGRESS,
    ]:
        messages.error(request, "Цей запит не можна скасувати.")
        return redirect("requests:detail", pk=pk)

    with transaction.atomic():
        help_request.status = HelpRequest.Status.CANCELLED
        help_request.save()

    messages.warning(request, "Запит скасовано.")
    return redirect("requests:my-requests")
