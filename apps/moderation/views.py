"""
On-site moderation (ROADMAP stage 4).

Users: apply for verification, redeem an organization code, report content.
Moderators (group "Модератори"): one queue with verification applications,
premoderated requests and reports; invite code management.
"""

from collections import Counter
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import is_moderator
from apps.requests import services as request_services
from apps.requests.models import HelpRequest

from . import services
from .forms import DecisionForm, InviteCodeForm, InviteRedeemForm, ReportForm, VerificationForm
from .models import InviteCode, Report, VerificationRequest


def moderator_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_moderator(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def _note(request):
    form = DecisionForm(request.POST)
    return form.cleaned_data["note"] if form.is_valid() else ""


# ---------------------------------------------------------------------------
# User side
# ---------------------------------------------------------------------------


@login_required
def apply_for_verification(request):
    error = services.application_error(request.user)
    if error:
        messages.info(request, error)
        return redirect("accounts:profile")
    form = VerificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.apply(request.user, **form.cleaned_data)
        except services.ModerationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Заявку надіслано. Модератор розгляне її найближчим часом.")
        return redirect("accounts:profile")
    return render(
        request,
        "moderation/apply.html",
        {"form": form, "code_form": InviteRedeemForm()},
    )


@login_required
@require_POST
def redeem_code(request):
    form = InviteRedeemForm(request.POST)
    if form.is_valid():
        try:
            organization = services.redeem_invite(request.user, form.cleaned_data["code"])
        except services.ModerationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Вітаємо! Ви перевірені від імені «{organization}».")
    return redirect("accounts:profile")


@login_required
def report(request, kind, pk):
    model = services.REPORTABLE.get(kind)
    if model is None:
        raise Http404
    target = get_object_or_404(model, pk=pk)
    if not services.can_report(request.user, kind, target):
        raise Http404
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""
    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.file_report(
                request.user, target, form.cleaned_data["reason"], form.cleaned_data["comment"]
            )
        except services.ModerationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Дякуємо! Модератор розгляне скаргу.")
        return redirect(next_url or "home")
    return render(
        request,
        "moderation/report.html",
        {"form": form, "target_label": services.REPORT_LABELS[kind], "next": next_url},
    )


# ---------------------------------------------------------------------------
# Moderator side
# ---------------------------------------------------------------------------


@moderator_required
def queue(request):
    tab = request.GET.get("tab", "verification")
    counts = {
        "verification": VerificationRequest.objects.filter(
            status=VerificationRequest.Status.PENDING
        ).count(),
        "requests": HelpRequest.objects.filter(
            status=HelpRequest.Status.PENDING_MODERATION
        ).count(),
        "reports": Report.objects.filter(status=Report.Status.OPEN).count(),
    }
    context = {"tab": tab, "counts": counts, "decision_form": DecisionForm()}
    if tab == "requests":
        context["items"] = (
            HelpRequest.objects.filter(status=HelpRequest.Status.PENDING_MODERATION)
            .select_related("recipient", "category")
            .order_by("created_at")
        )
    elif tab == "reports":
        reports = list(
            Report.objects.filter(status=Report.Status.OPEN)
            .select_related("reporter", "content_type")
            .order_by("created_at")
        )
        # Several people reporting the same thing is a strong signal
        similar = Counter((r.content_type_id, r.object_id) for r in reports)
        for item in reports:
            item.measure = services.measure_label(item.target) if item.target else ""
            item.similar = similar[(item.content_type_id, item.object_id)]
        context["items"] = reports
    else:
        context["tab"] = "verification"
        context["items"] = (
            VerificationRequest.objects.filter(status=VerificationRequest.Status.PENDING)
            .select_related("user")
            .order_by("created_at")
        )
    return render(request, "moderation/queue.html", context)


@moderator_required
@require_POST
def decide_verification(request, pk):
    application = get_object_or_404(VerificationRequest, pk=pk)
    try:
        if request.POST.get("decision") == "approve":
            services.approve_verification(application, request.user, _note(request))
            messages.success(request, "Заявку схвалено.")
        else:
            services.reject_verification(application, request.user, _note(request))
            messages.info(request, "Заявку відхилено.")
    except services.ModerationError as exc:
        messages.error(request, str(exc))
    return redirect("moderation:queue")


@moderator_required
@require_POST
def decide_request(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk)
    try:
        if request.POST.get("decision") == "approve":
            request_services.approve(help_request, request.user)
            messages.success(request, "Запит опубліковано.")
        else:
            request_services.reject_request(help_request, request.user, _note(request))
            messages.info(request, "Запит відхилено.")
    except request_services.TransitionError as exc:
        messages.error(request, str(exc))
    return redirect("/moderation/?tab=requests")


@moderator_required
@require_POST
def decide_report(request, pk):
    item = get_object_or_404(Report, pk=pk)
    try:
        if request.POST.get("decision") == "act":
            services.act_on_report(item, request.user, _note(request))
            messages.success(request, "Заходів ужито, скаргу закрито.")
        else:
            services.dismiss_report(item, request.user, _note(request))
            messages.info(request, "Скаргу відхилено.")
    except services.ModerationError as exc:
        messages.error(request, str(exc))
    return redirect("/moderation/?tab=reports")


@moderator_required
@require_POST
def revoke(request, pk):
    user = get_object_or_404(User, pk=pk)
    try:
        removed = services.revoke_verification(user, request.user, _note(request))
    except services.ModerationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Статус відкликано. Знято з відкритих запитів: {removed}.")
    return redirect("accounts:public-profile", pk=pk)


@moderator_required
def invite_codes(request):
    form = InviteCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = form.save(commit=False)
        code.created_by = request.user
        code.save()
        messages.success(request, f"Створено код {code.code} для «{code.organization}».")
        return redirect("moderation:codes")
    return render(
        request,
        "moderation/codes.html",
        {"form": form, "codes": InviteCode.objects.select_related("created_by")[:50]},
    )


@moderator_required
@require_POST
def deactivate_code(request, pk):
    InviteCode.objects.filter(pk=pk).update(is_active=False)
    messages.info(request, "Код деактивовано.")
    return redirect("moderation:codes")
