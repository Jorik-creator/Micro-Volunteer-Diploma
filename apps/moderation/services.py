"""
Trust & safety: verification (L2), invite codes and reports.

See docs/adr/0001 (no identity documents) and 0002 (trust levels).
"""

from contextlib import suppress
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.requests import services as request_services
from apps.requests.models import HelpRequest, Response
from apps.reviews.models import Review

from .models import InviteCode, Report, VerificationRequest

REAPPLY_AFTER = timedelta(days=7)
VStatus = VerificationRequest.Status


class ModerationError(Exception):
    """The action is not allowed."""


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def latest_verification(user):
    return user.verification_requests.first()


def application_error(user, now=None):
    """Why the user cannot apply for verification right now, or None."""
    now = now or timezone.now()
    if user.is_verified:
        return "Ви вже перевірені."
    if user.trust_level < User.TrustLevel.EMAIL_CONFIRMED:
        return "Спершу підтвердіть email."
    latest = latest_verification(user)
    if latest and latest.status == VStatus.PENDING:
        return "Вашу заявку вже розглядає модератор."
    if latest and latest.status in (VStatus.REJECTED, VStatus.REVOKED):
        retry_at = latest.reviewed_at + REAPPLY_AFTER
        if now < retry_at:
            return f"Повторно подати заявку можна після {timezone.localtime(retry_at):%d.%m.%Y}."
    return None


def apply(user, **answers):
    error = application_error(user)
    if error:
        raise ModerationError(error)
    try:
        return VerificationRequest.objects.create(user=user, **answers)
    except IntegrityError as exc:
        raise ModerationError("Вашу заявку вже розглядає модератор.") from exc


def _set_verified(user, value):
    user.is_verified = value
    user.save(update_fields=["is_verified"])


@transaction.atomic
def approve_verification(application, moderator, note=""):
    application = VerificationRequest.objects.select_for_update().get(pk=application.pk)
    if application.status != VStatus.PENDING:
        raise ModerationError("Заявку вже розглянуто.")
    application.status = VStatus.APPROVED
    application.reviewed_by = moderator
    application.reviewed_at = timezone.now()
    application.decision_reason = note[:500]
    application.save()
    _set_verified(application.user, True)
    notify(
        application.user,
        Notification.Type.VERIFICATION_DECISION,
        "Ви пройшли перевірку ✓",
        "Тепер у вашому профілі є бейдж «Перевірений»"
        + (
            ", і ви можете відгукуватися на запити з візитом додому."
            if application.user.is_volunteer
            else ", а ваші запити публікуються без премодерації."
        ),
    )


@transaction.atomic
def reject_verification(application, moderator, reason):
    if not reason.strip():
        raise ModerationError("Вкажіть причину — користувач побачить її.")
    application = VerificationRequest.objects.select_for_update().get(pk=application.pk)
    if application.status != VStatus.PENDING:
        raise ModerationError("Заявку вже розглянуто.")
    application.status = VStatus.REJECTED
    application.reviewed_by = moderator
    application.reviewed_at = timezone.now()
    application.decision_reason = reason[:500]
    application.save()
    notify(
        application.user,
        Notification.Type.VERIFICATION_DECISION,
        "Заявку на перевірку відхилено",
        f"Причина: {reason}. Ви зможете подати нову заявку через 7 днів.",
    )


def revoke_verification(user, moderator, reason):
    """
    Take L2 away. An approved application becomes "revoked" (history kept);
    the volunteer is taken off every open request (ROADMAP, Q11).
    """
    if not user.is_verified:
        raise ModerationError("Користувач не має статусу «Перевірений».")
    if not reason.strip():
        raise ModerationError("Вкажіть причину відкликання.")
    with transaction.atomic():
        latest = user.verification_requests.filter(status=VStatus.APPROVED).first()
        if latest:
            latest.status = VStatus.REVOKED
            latest.reviewed_by = moderator
            latest.reviewed_at = timezone.now()
            latest.decision_reason = reason[:500]
            latest.save()
        else:  # verified by an admin directly: still keep a trace
            VerificationRequest.objects.create(
                user=user,
                status=VStatus.REVOKED,
                city="—",
                about="Статус надано поза заявкою",
                reviewed_by=moderator,
                reviewed_at=timezone.now(),
                decision_reason=reason[:500],
            )
        _set_verified(user, False)
    removed = 0
    open_responses = Response.objects.filter(
        volunteer=user,
        status__in=[Response.Status.PENDING, Response.Status.ACCEPTED],
        help_request__status__in=HelpRequest.OPEN_STATUSES,
    )
    for response in open_responses:
        if request_services.remove_by_moderator(response, "Статус перевірки відкликано."):
            removed += 1
    notify(
        user,
        Notification.Type.VERIFICATION_DECISION,
        "Статус «Перевірений» відкликано",
        f"Причина: {reason}",
    )
    return removed


@transaction.atomic
def redeem_invite(user, raw_code):
    if user.is_verified:
        raise ModerationError("Ви вже перевірені.")
    if user.trust_level < User.TrustLevel.EMAIL_CONFIRMED:
        raise ModerationError("Спершу підтвердіть email.")
    code = (
        InviteCode.objects.select_for_update()
        .filter(code=raw_code.strip().upper().replace(" ", ""))
        .first()
    )
    if code is None or not code.is_usable:
        raise ModerationError("Код недійсний, використаний або прострочений.")
    code.uses_count += 1
    code.save(update_fields=["uses_count"])
    user.verification_requests.filter(status=VStatus.PENDING).update(
        status=VStatus.APPROVED, reviewed_at=timezone.now(), decision_reason="Код організації"
    )
    VerificationRequest.objects.create(
        user=user,
        status=VStatus.APPROVED,
        city="—",
        about=f"Код організації {code.organization}",
        organization=code.organization,
        invite_code=code,
        reviewed_at=timezone.now(),
        decision_reason="Код організації",
    )
    _set_verified(user, True)
    return code.organization


def verified_organization(user):
    """Organization that vouched for the user via an invite code, if any."""
    if not user.is_verified:
        return ""
    approved = user.verification_requests.filter(status=VStatus.APPROVED).first()
    return approved.organization if approved and approved.invite_code_id else ""


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


REPORTABLE = {
    "request": HelpRequest,
    "user": User,
    "review": Review,
}


def register_reportable(key, model):
    """Other apps (e.g. conversations) add their models here."""
    REPORTABLE[key] = model


def file_report(reporter, target, reason, comment=""):
    from django.contrib.contenttypes.models import ContentType

    if getattr(target, "pk", None) == reporter.pk and isinstance(target, User):
        raise ModerationError("Не можна поскаржитися на себе.")
    try:
        return Report.objects.create(
            reporter=reporter,
            content_type=ContentType.objects.get_for_model(target),
            object_id=target.pk,
            reason=reason,
            comment=comment.strip(),
        )
    except IntegrityError as exc:
        raise ModerationError("Ви вже поскаржилися — модератор розгляне скаргу.") from exc


def _close_report(report, moderator, status, resolution):
    report.status = status
    report.resolved_by = moderator
    report.resolved_at = timezone.now()
    report.resolution = resolution[:500]
    report.save()
    # Close duplicates from other reporters about the same object
    Report.objects.filter(
        content_type=report.content_type, object_id=report.object_id, status=Report.Status.OPEN
    ).update(
        status=status,
        resolved_by=moderator,
        resolved_at=report.resolved_at,
        resolution=report.resolution,
    )
    notify(
        report.reporter,
        Notification.Type.REPORT_RESOLVED,
        "Скаргу розглянуто",
        "Дякуємо! Модератор розглянув вашу скаргу"
        + (" і вжив заходів." if status == Report.Status.RESOLVED else ", порушень не виявлено."),
    )


def dismiss_report(report, moderator, note=""):
    if report.status != Report.Status.OPEN:
        raise ModerationError("Скаргу вже розглянуто.")
    _close_report(report, moderator, Report.Status.DISMISSED, note or "Порушень не виявлено")


def act_on_report(report, moderator, note=""):
    """Apply the standard measure for the reported object and close the report."""
    if report.status != Report.Status.OPEN:
        raise ModerationError("Скаргу вже розглянуто.")
    target = report.target
    reason = note or report.get_reason_display()
    if target is None:
        pass  # already deleted
    elif isinstance(target, HelpRequest):
        # An already closed request needs no further action
        with suppress(request_services.TransitionError):
            request_services.cancel_by_moderator(target, reason)
    elif isinstance(target, User):
        if target.is_verified:
            revoke_verification(target, moderator, reason)
        target.is_active = False
        target.save(update_fields=["is_active"])
    elif isinstance(target, Review):
        target.hidden_at = timezone.now()
        target.save(update_fields=["hidden_at"])
    elif hasattr(target, "hide"):
        target.hide()
    _close_report(report, moderator, Report.Status.RESOLVED, reason)


MEASURES = {
    HelpRequest: "Закрити запит",
    User: "Заблокувати користувача",
    Review: "Приховати оцінку",
}


def measure_label(target):
    for model, label in MEASURES.items():
        if isinstance(target, model):
            return label
    return getattr(target, "moderation_measure", "Приховати")
