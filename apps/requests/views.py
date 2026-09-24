"""
Views for the requests app.

Views stay thin: they check the role, parse input and hand the actual state
change to apps.requests.services, turning TransitionError into a message.

Public browsing:
  HelpRequestListView, MapView, map_data, HelpRequestDetailView, request_status

Recipient:
  HelpRequestCreateView, HelpRequestUpdateView, MyRequestsView,
  accept_volunteer, reject_volunteer, remove_volunteer,
  confirm_completion, dispute_completion, cancel_request

Volunteer:
  MyResponsesView, respond_to_request, withdraw_response, complete_request
"""

import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.accounts.decorators import recipient_required, volunteer_required
from apps.accounts.permissions import is_moderator
from apps.conversations.models import Conversation
from apps.reviews import services as review_services
from apps.reviews.models import Review

from . import services
from .forms import FilterForm, HelpRequestForm, ReasonForm, ResponseForm
from .models import HelpRequest, Response
from .services import TransitionError
from .utils import offset_coordinates


def _perform(request, action, *args, success=None, **kwargs):
    """Run a service call and report the outcome as a flash message."""
    try:
        result = action(*args, **kwargs)
    except TransitionError as error:
        messages.error(request, str(error))
        return None
    if success:
        messages.success(request, success)
    return result


def _reason(request):
    form = ReasonForm(request.POST)
    return form.cleaned_data["reason"] if form.is_valid() else ""


PUBLISH_MESSAGES = {
    HelpRequest.Status.DRAFT: "Чернетку збережено. Підтвердіть email, щоб опублікувати запит.",
    HelpRequest.Status.PENDING_MODERATION: (
        "Запит надіслано на перевірку модератору. Зазвичай це займає кілька годин."
    ),
    HelpRequest.Status.ACTIVE: "Запит опубліковано! Волонтери поблизу вже отримали сповіщення.",
}


class RecipientOnlyMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_recipient:
            messages.error(request, "Ця сторінка доступна тільки для отримувачів допомоги.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)


class VolunteerOnlyMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_volunteer:
            messages.error(request, "Ця сторінка доступна тільки для волонтерів.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# List & Map views (public browsing)
# ---------------------------------------------------------------------------


class HelpRequestListView(ListView):
    """Paginated list of active help requests with optional filters."""

    template_name = "requests/request_list.html"
    context_object_name = "requests"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            HelpRequest.objects.filter(status=HelpRequest.Status.ACTIVE)
            .select_related("recipient", "category")
            .ordered_by_urgency()
        )
        form = FilterForm(self.request.GET)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("category"):
                qs = qs.filter(category=data["category"])
            if data.get("urgency"):
                qs = qs.filter(urgency=data["urgency"])
            if data.get("duration"):
                qs = qs.filter(duration=data["duration"])
            if data.get("date_from"):
                qs = qs.filter(needed_date__date__gte=data["date_from"])
            if data.get("date_to"):
                qs = qs.filter(needed_date__date__lte=data["date_to"])
            if data.get("city"):
                # Only the public city field — never the private address (it could be probed)
                qs = qs.filter(city__icontains=data["city"])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = FilterForm(self.request.GET)
        # Keep active filters in pagination links without duplicating "page"
        query = self.request.GET.copy()
        query.pop("page", None)
        context["filter_query"] = query.urlencode()
        return context


class MapView(TemplateView):
    """Leaflet map page — data loaded via AJAX from map_data endpoint."""

    template_name = "requests/map.html"


def _private_seed(pk):
    """
    Stable per request (averaging repeated polls gains nothing) but not
    derivable from the public id — seeding with pk alone let anyone undo it.
    """
    return hmac.new(settings.SECRET_KEY.encode(), f"map:{pk}".encode(), "sha256").hexdigest()


def map_data(request):
    """Return active requests as JSON for Leaflet map markers."""
    active = HelpRequest.objects.filter(
        status=HelpRequest.Status.ACTIVE,
        latitude__isnull=False,
        longitude__isnull=False,
    ).select_related("category")

    data = []
    for hr in active:
        # Offset coordinates for privacy. Seed with the request pk so the
        # offset is stable across repeated calls (prevents averaging out
        # the true location by polling the endpoint multiple times).
        lat, lon = offset_coordinates(
            hr.latitude, hr.longitude, offset_meters=150, seed=_private_seed(hr.pk)
        )
        data.append(
            {
                "id": hr.pk,
                "title": hr.title,
                "urgency": hr.urgency,
                "urgency_display": hr.get_urgency_display(),
                "category": hr.category.name if hr.category else "",
                "needed_date": hr.needed_date.strftime("%d.%m.%Y %H:%M"),
                "duration": hr.get_duration_display(),
                "lat": lat,
                "lon": lon,
                "url": reverse("requests:detail", args=[hr.pk]),
            }
        )

    return JsonResponse(data, safe=False)


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------


class HelpRequestDetailView(DetailView):
    """
    Full request details. Anyone may open an active request; the owner and
    volunteers who responded may open it in any status (others get 404).
    """

    template_name = "requests/request_detail.html"
    context_object_name = "help_request"

    def get_queryset(self):
        if is_moderator(self.request.user):
            return HelpRequest.objects.select_related("recipient", "category")
        return HelpRequest.objects.visible_to(self.request.user).select_related(
            "recipient", "category"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hr = self.object
        user = self.request.user

        responses = list(hr.responses.select_related("volunteer").order_by("created_at"))
        accepted = [r for r in responses if r.status == Response.Status.ACCEPTED]
        is_owner = user.is_authenticated and hr.recipient_id == user.pk
        user_response = next(
            (r for r in responses if user.is_authenticated and r.volunteer_id == user.pk), None
        )
        is_accepted = bool(user_response and user_response.status == Response.Status.ACCEPTED)

        trust_error = (
            services.respond_trust_error(user, hr)
            if user.is_authenticated and user.is_volunteer
            else None
        )
        context.update(
            {
                "lifecycle": lifecycle_steps(hr, len(accepted)),
                "respond_blocked_reason": trust_error,
                "is_moderator": is_moderator(user),
                "response_form": ResponseForm(),
                "reason_form": ReasonForm(),
                "accepted_count": len(accepted),
                "accepted_responses": accepted,
                "is_owner": is_owner,
                "user_response": user_response,
                "is_accepted": is_accepted,
                # Recipient PII is only revealed to the owner or an accepted volunteer
                "can_view_recipient": is_owner or is_accepted,
                "can_respond": (
                    user.is_authenticated
                    and user.is_volunteer
                    and hr.status == HelpRequest.Status.ACTIVE
                    and user_response is None
                ),
            }
        )
        if hr.completed_at and (is_owner or is_accepted):
            context.update(_review_context(hr, user))
        conversations = {
            c.volunteer_id: c.pk
            for c in Conversation.objects.filter(help_request=hr).only("pk", "volunteer_id")
        }
        for response in responses:
            response.conversation_id = conversations.get(response.volunteer_id)
        if is_accepted:
            context["my_conversation"] = Conversation.objects.filter(
                help_request=hr, volunteer=user
            ).first()
        if is_owner:
            context["responses"] = sorted(
                responses,
                key=lambda r: (r.status != Response.Status.ACCEPTED, r.status != "pending"),
            )
        return context


def lifecycle_steps(help_request, accepted_count):
    """
    Steps for the progress bar on the request page. Returns None for closed
    requests (cancelled / expired / rejected), which get a banner instead.
    """
    s = HelpRequest.Status
    status = help_request.status
    if status in (s.CANCELLED, s.EXPIRED, s.REJECTED):
        return None
    order = {
        s.DRAFT: 0,
        s.PENDING_MODERATION: 0,
        s.ACTIVE: 1,
        s.IN_PROGRESS: 2,
        s.AWAITING_CONFIRMATION: 2,
        s.COMPLETED: 3,
    }[status]
    first_note = {
        s.DRAFT: "чернетка",
        s.PENDING_MODERATION: "на перевірці",
    }.get(
        status,
        help_request.published_at and f"{timezone.localtime(help_request.published_at):%d.%m}",
    )
    notes = [
        first_note or "",
        f"{accepted_count} з {help_request.volunteers_needed}",
        "очікує підтвердження"
        if status == s.AWAITING_CONFIRMATION
        else f"{timezone.localtime(help_request.needed_date):%d.%m, %H:%M}",
        "залиште оцінку" if status == s.COMPLETED else "",
    ]
    labels = ["Опубліковано", "Волонтерів набрано", "Допомога", "Завершено"]
    steps = []
    for index, (label, note) in enumerate(zip(labels, notes, strict=True)):
        if index < order or (index == order == 3):
            state = "done"
        elif index == order:
            state = "current"
        else:
            state = "todo"
        steps.append({"number": index + 1, "label": label, "note": note, "state": state})
    return steps


def _review_context(help_request, user):
    """Who the participant can still rate on a completed request."""
    written = set(
        Review.objects.filter(author=user, help_request=help_request).values_list(
            "target_id", flat=True
        )
    )
    deadline = review_services.review_deadline(help_request)
    return {
        "review_items": [
            {"target": target, "done": target.pk in written}
            for target in review_services.counterparts(help_request, user)
        ],
        "review_deadline": deadline,
        "review_open": timezone.now() <= deadline,
    }


def request_status(request, pk):
    """Current status as JSON for polling; same visibility rules as the detail page."""
    help_request = get_object_or_404(HelpRequest.objects.visible_to(request.user), pk=pk)
    return JsonResponse(
        {
            "status": help_request.status,
            "status_display": help_request.get_status_display(),
        }
    )


# ---------------------------------------------------------------------------
# Create / Update (recipients only)
# ---------------------------------------------------------------------------


class HelpRequestCreateView(RecipientOnlyMixin, CreateView):
    """Create a new help request. Only recipients, limited number of open requests."""

    model = HelpRequest
    form_class = HelpRequestForm
    template_name = "requests/request_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_recipient:
            error = services.can_create_request(request.user)
            if error:
                messages.error(request, error)
                return redirect("requests:my-requests")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        self.object = services.create_request(form.save(commit=False), self.request.user)
        messages.success(self.request, PUBLISH_MESSAGES[self.object.status])
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("requests:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Створити запит допомоги"
        context["submit_label"] = "Створити запит"
        context["cancel_url"] = reverse("requests:my-requests")
        context["help_format_hints"] = HelpRequest.HELP_FORMAT_HINTS
        return context


class HelpRequestUpdateView(LoginRequiredMixin, UpdateView):
    """Edit an active help request (owner only)."""

    model = HelpRequest
    form_class = HelpRequestForm
    template_name = "requests/request_form.html"

    def get_queryset(self):
        return HelpRequest.objects.filter(recipient=self.request.user)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            obj = get_object_or_404(HelpRequest, pk=kwargs["pk"])
            if obj.recipient_id != request.user.pk:
                messages.error(request, "У вас немає доступу до цього запиту.")
                return redirect("home")
            if not obj.is_editable:
                messages.error(request, "Редагування недоступне для цього статусу запиту.")
                return redirect("requests:detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        error = services.editable_fields_error(
            self.object, form.changed_data, form.cleaned_data["volunteers_needed"]
        )
        if error:
            form.add_error(None, error)
            return self.form_invalid(form)
        response = super().form_valid(form)
        services.after_edit(self.object, form.changed_data)
        self.object.refresh_from_db()
        if self.object.status == HelpRequest.Status.PENDING_MODERATION:
            messages.info(self.request, "Запит оновлено й надіслано на повторну перевірку.")
        else:
            messages.success(self.request, "Запит оновлено.")
        return response

    def get_success_url(self):
        return reverse("requests:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Редагувати запит"
        context["submit_label"] = "Зберегти зміни"
        context["cancel_url"] = reverse("requests:detail", kwargs={"pk": self.object.pk})
        context["help_format_hints"] = HelpRequest.HELP_FORMAT_HINTS
        return context


# ---------------------------------------------------------------------------
# Personal dashboards
# ---------------------------------------------------------------------------


class MyRequestsView(RecipientOnlyMixin, ListView):
    """Recipient sees all their own requests."""

    template_name = "requests/my_requests.html"
    context_object_name = "requests"
    paginate_by = 10

    def get_queryset(self):
        return (
            HelpRequest.objects.filter(recipient=self.request.user)
            .select_related("category")
            .annotate(
                pending_count=Count("responses", filter=Q(responses__status="pending")),
            )
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = HelpRequest.objects.filter(recipient=self.request.user).aggregate(
            active=Count("pk", filter=Q(status=HelpRequest.Status.ACTIVE)),
            in_progress=Count(
                "pk",
                filter=Q(
                    status__in=[
                        HelpRequest.Status.IN_PROGRESS,
                        HelpRequest.Status.AWAITING_CONFIRMATION,
                    ]
                ),
            ),
            completed=Count("pk", filter=Q(status=HelpRequest.Status.COMPLETED)),
        )
        context["active_count"] = counts["active"]
        context["in_progress_count"] = counts["in_progress"]
        context["completed_count"] = counts["completed"]
        return context


class MyResponsesView(VolunteerOnlyMixin, ListView):
    """Volunteer sees every request they responded to, current ones first."""

    template_name = "requests/my_responses.html"
    context_object_name = "responses"
    paginate_by = 10

    def get_queryset(self):
        return (
            Response.objects.filter(volunteer=self.request.user)
            .select_related("help_request", "help_request__category")
            .order_by("-help_request__status_changed_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mine = Response.objects.filter(volunteer=self.request.user)
        context["current_count"] = mine.filter(
            status__in=[Response.Status.PENDING, Response.Status.ACCEPTED],
            help_request__status__in=HelpRequest.OPEN_STATUSES,
        ).count()
        context["helped_count"] = mine.filter(
            status=Response.Status.ACCEPTED,
            help_request__status=HelpRequest.Status.COMPLETED,
        ).count()
        return context


# ---------------------------------------------------------------------------
# Volunteer actions
# ---------------------------------------------------------------------------


@volunteer_required
@require_POST
def respond_to_request(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk)
    form = ResponseForm(request.POST)
    if form.is_valid():
        _perform(
            request,
            services.respond,
            help_request,
            request.user,
            form.cleaned_data["message"],
            success="Ваш відгук надіслано! Очікуйте підтвердження.",
        )
    return redirect("requests:detail", pk=pk)


@volunteer_required
@require_POST
def withdraw_response(request, pk):
    response = get_object_or_404(Response, help_request_id=pk, volunteer=request.user)
    _perform(
        request,
        services.withdraw,
        response,
        request.user,
        _reason(request),
        success="Ви вийшли із запиту.",
    )
    return redirect("requests:detail", pk=pk)


@login_required
@require_POST
def complete_request(request, pk):
    """The accepted volunteer marks their part as done."""
    response = Response.objects.filter(help_request_id=pk, volunteer=request.user).first()
    if response is None:
        messages.error(request, "Тільки прийнятий волонтер може позначити запит виконаним.")
    else:
        _perform(
            request,
            services.mark_done,
            response,
            request.user,
            success="Дякуємо! Отримувач підтвердить завершення.",
        )
    return redirect("requests:detail", pk=pk)


# ---------------------------------------------------------------------------
# Recipient actions
# ---------------------------------------------------------------------------


def _own_response(request, response_id):
    return get_object_or_404(Response, pk=response_id, help_request__recipient=request.user)


@recipient_required
@require_POST
def accept_volunteer(request, response_id):
    response = _own_response(request, response_id)
    accepted = _perform(request, services.accept, response, request.user)
    if accepted is not None:
        response.help_request.refresh_from_db()
        needed = response.help_request.volunteers_needed
        if accepted >= needed:
            messages.success(request, "Волонтерів набрано — запит перейшов у роботу.")
        else:
            messages.success(request, f"Волонтера прийнято ({accepted}/{needed}).")
    return redirect("requests:detail", pk=response.help_request_id)


@recipient_required
@require_POST
def reject_volunteer(request, response_id):
    response = _own_response(request, response_id)
    _perform(request, services.reject, response, request.user, success="Відгук відхилено.")
    return redirect("requests:detail", pk=response.help_request_id)


@recipient_required
@require_POST
def remove_volunteer(request, response_id):
    response = _own_response(request, response_id)
    reopened = _perform(
        request,
        services.remove,
        response,
        request.user,
        _reason(request),
        success="Волонтера знято із запиту.",
    )
    if reopened:
        messages.info(request, "Запит знову відкрито для волонтерів.")
    return redirect("requests:detail", pk=response.help_request_id)


@recipient_required
@require_POST
def confirm_completion(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk, recipient=request.user)
    _perform(
        request,
        services.confirm_completion,
        help_request,
        request.user,
        success="Запит завершено. Дякуємо! Не забудьте оцінити волонтерів.",
    )
    return redirect("requests:detail", pk=pk)


@recipient_required
@require_POST
def dispute_completion(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk, recipient=request.user)
    _perform(
        request,
        services.dispute_completion,
        help_request,
        request.user,
        _reason(request),
        success="Волонтерам повідомлено, що допомогу ще не завершено.",
    )
    return redirect("requests:detail", pk=pk)


@recipient_required
@require_POST
def publish_request(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk, recipient=request.user)
    try:
        status = services.publish(help_request, request.user)
    except TransitionError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, PUBLISH_MESSAGES[status])
    return redirect("requests:detail", pk=pk)


@recipient_required
@require_POST
def cancel_request(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk, recipient=request.user)
    try:
        services.cancel(help_request, request.user)
    except TransitionError as error:
        messages.error(request, str(error))
        return redirect("requests:detail", pk=pk)
    messages.warning(request, "Запит скасовано.")
    return redirect("requests:my-requests")
