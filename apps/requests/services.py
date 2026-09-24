"""
Help request lifecycle.

Every state change of a HelpRequest or a volunteer Response goes through a
function in this module. Each function:
  - locks the request row, so concurrent clicks cannot overfill or corrupt it;
  - checks that the actor is allowed to do it and the transition is legal;
  - notifies everyone affected explicitly (no model signals, see ADR 0003).

Views translate TransitionError into a user-facing message.
See docs/ROADMAP.md for the state diagram.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import notify, notify_many, notify_nearby_volunteers

from .models import HelpRequest, Response

Status = HelpRequest.Status
RStatus = Response.Status

MAX_ACTIVE_REQUESTS = 10
PREMODERATED_REQUESTS = 3  # first requests of a not-yet-verified recipient (ADR 0002)
CANCELLABLE = (Status.DRAFT, Status.PENDING_MODERATION, *HelpRequest.OPEN_STATUSES)
AUTO_CONFIRM_AFTER = timedelta(hours=72)
REMIND_AFTER_END = timedelta(hours=24)
EXPIRE_IN_PROGRESS_AFTER_END = timedelta(days=7)


class TransitionError(Exception):
    """The requested action is not allowed in the current state or for this user."""


def _name(user):
    return user.get_full_name() or user.username


def _lock(help_request):
    """Re-read the request with a row lock inside the current transaction."""
    return HelpRequest.objects.select_for_update().get(pk=help_request.pk)


def _lock_response(response):
    """Lock the parent request first, then re-read the response."""
    help_request = _lock(response.help_request)
    response = Response.objects.select_related("volunteer").get(pk=response.pk)
    response.help_request = help_request
    return help_request, response


def _set_status(help_request, status, now=None):
    now = now or timezone.now()
    help_request.status = status
    help_request.status_changed_at = now
    fields = ["status", "status_changed_at", "updated_at"]
    if status == Status.COMPLETED:
        help_request.completed_at = now
        fields.append("completed_at")
    help_request.save(update_fields=fields)


def _set_response_status(response, status, reason=""):
    response.status = status
    response.status_reason = reason[:300]
    response.save(update_fields=["status", "status_reason"])


def _close_pending(help_request, reason):
    """Close every still-pending response and tell those volunteers."""
    pending = list(
        help_request.responses.filter(status=RStatus.PENDING).select_related("volunteer")
    )
    help_request.responses.filter(pk__in=[r.pk for r in pending]).update(
        status=RStatus.CLOSED, status_reason=reason
    )
    return [r.volunteer for r in pending]


def _accepted_volunteers(help_request):
    return [r.volunteer for r in help_request.accepted_responses().select_related("volunteer")]


# ---------------------------------------------------------------------------
# Creating and editing
# ---------------------------------------------------------------------------


def can_create_request(user):
    """Return an error message when the recipient may not create one more request."""
    open_count = HelpRequest.objects.filter(recipient=user, status__in=CANCELLABLE)
    if open_count.count() >= MAX_ACTIVE_REQUESTS:
        return (
            f"Досягнуто максимум відкритих запитів ({MAX_ACTIVE_REQUESTS}). "
            "Завершіть або скасуйте деякі перед створенням нового."
        )
    return None


def needs_premoderation(recipient):
    if recipient.is_verified:
        return False
    published = HelpRequest.objects.filter(recipient=recipient, published_at__isnull=False)
    return published.count() < PREMODERATED_REQUESTS


def _go_live(help_request):
    help_request.published_at = timezone.now()
    help_request.save(update_fields=["published_at"])
    _set_status(help_request, Status.ACTIVE)
    transaction.on_commit(lambda: notify_nearby_volunteers(help_request))


def create_request(help_request, recipient):
    """
    Save a new request built from a form. Depending on the recipient's trust
    level it stays a draft (email not confirmed), goes to premoderation or is
    published right away (ADR 0002).
    """
    help_request.recipient = recipient
    help_request.status = Status.DRAFT
    help_request.save()
    if recipient.trust_level >= recipient.TrustLevel.EMAIL_CONFIRMED:
        publish(help_request, recipient)
        help_request.refresh_from_db()
    return help_request


@transaction.atomic
def publish(help_request, recipient):
    help_request = _lock(help_request)
    if help_request.recipient_id != recipient.pk:
        raise TransitionError("Це не ваш запит.")
    if help_request.status != Status.DRAFT:
        raise TransitionError("Опублікувати можна лише чернетку.")
    if recipient.trust_level < recipient.TrustLevel.EMAIL_CONFIRMED:
        raise TransitionError("Підтвердіть email, щоб опублікувати запит.")
    if help_request.needed_date < timezone.now():
        raise TransitionError("Дата допомоги вже минула — змініть її перед публікацією.")

    if needs_premoderation(recipient):
        _set_status(help_request, Status.PENDING_MODERATION)
    else:
        _go_live(help_request)
    return help_request.status


@transaction.atomic
def approve(help_request, moderator):
    help_request = _lock(help_request)
    if help_request.status != Status.PENDING_MODERATION:
        raise TransitionError("Запит не очікує модерації.")
    help_request.moderation_note = ""
    help_request.save(update_fields=["moderation_note"])
    _go_live(help_request)
    notify(
        help_request.recipient,
        Notification.Type.REQUEST_APPROVED,
        "Запит опубліковано",
        f"Модератор перевірив запит «{help_request.title}». Волонтери поблизу вже його бачать.",
        help_request,
    )


@transaction.atomic
def reject_request(help_request, moderator, reason):
    help_request = _lock(help_request)
    if help_request.status != Status.PENDING_MODERATION:
        raise TransitionError("Запит не очікує модерації.")
    if not reason.strip():
        raise TransitionError("Вкажіть причину, щоб отримувач міг виправити запит.")
    help_request.moderation_note = reason[:300]
    help_request.save(update_fields=["moderation_note"])
    _set_status(help_request, Status.REJECTED)
    notify(
        help_request.recipient,
        Notification.Type.REQUEST_REJECTED_BY_MODERATOR,
        "Запит не пройшов модерацію",
        f"Запит «{help_request.title}» не опубліковано. Причина: {reason}",
        help_request,
    )


LOCKED_WHEN_RESPONDED = ("needed_date", "address", "latitude", "longitude")


def editable_fields_error(help_request, changed_fields, new_volunteers_needed):
    """
    Validate an edit of an active request that already has responses.
    Volunteers agreed to a specific time and place, so those are frozen;
    the number of volunteers cannot drop below the already accepted ones.
    """
    if not help_request.is_editable:
        return "Редагувати цей запит уже не можна."
    has_responses = help_request.responses.filter(
        status__in=[RStatus.PENDING, RStatus.ACCEPTED]
    ).exists()
    if has_responses and set(changed_fields) & set(LOCKED_WHEN_RESPONDED):
        return (
            "На запит уже відгукнулися волонтери, тому дату й адресу змінити не можна. "
            "Скасуйте запит і створіть новий, якщо вони змінилися."
        )
    accepted = help_request.accepted_responses().count()
    if new_volunteers_needed < accepted:
        return f"Ви вже прийняли {accepted} волонтер(ів) — менше вказати не можна."
    return None


@transaction.atomic
def after_edit(help_request):
    """If the edit lowered volunteers_needed to the accepted count, start the work."""
    help_request = _lock(help_request)
    if (
        help_request.status == Status.ACTIVE
        and help_request.accepted_responses().count() >= help_request.volunteers_needed
    ):
        _start_work(help_request)


# ---------------------------------------------------------------------------
# Volunteer responses
# ---------------------------------------------------------------------------


def respond_trust_error(volunteer, help_request):
    """Trust-level gate for responding (ADR 0002), or None when allowed."""
    if volunteer.trust_level < volunteer.TrustLevel.EMAIL_CONFIRMED:
        return "Підтвердіть email у профілі, щоб відгукуватися на запити."
    if help_request.needs_verified_volunteer and not volunteer.is_verified:
        return (
            "Візит додому доступний лише перевіреним волонтерам. "
            "Подайте заявку на перевірку в профілі."
        )
    return None


@transaction.atomic
def respond(help_request, volunteer, message=""):
    help_request = _lock(help_request)
    if not volunteer.is_volunteer:
        raise TransitionError("Відгукнутися можуть лише волонтери.")
    trust_error = respond_trust_error(volunteer, help_request)
    if trust_error:
        raise TransitionError(trust_error)
    if help_request.recipient_id == volunteer.pk:
        raise TransitionError("Ви не можете відгукнутися на власний запит.")
    if help_request.status != Status.ACTIVE:
        raise TransitionError("Набір волонтерів на цей запит уже закрито.")

    response = Response.objects.filter(help_request=help_request, volunteer=volunteer).first()
    if response is not None:
        if response.status != RStatus.WITHDRAWN or response.done_at:
            raise TransitionError("Ви вже відгукнулися на цей запит.")
        # A volunteer who withdrew may change their mind while the request is still open.
        response.status = RStatus.PENDING
        response.status_reason = ""
        response.message = message
        response.save(update_fields=["status", "status_reason", "message"])
    else:
        response = Response.objects.create(
            help_request=help_request, volunteer=volunteer, message=message
        )

    notify(
        help_request.recipient,
        Notification.Type.NEW_RESPONSE,
        f"{_name(volunteer)} відгукнувся(лась) на ваш запит",
        f"Запит «{help_request.title}». Перегляньте відгук і прийміть або відхиліть його.",
        help_request,
    )
    return response


def _start_work(help_request):
    """Quota reached: move to in_progress and close the remaining pending responses."""
    _set_status(help_request, Status.IN_PROGRESS)
    closed = _close_pending(help_request, "Потрібну кількість волонтерів уже набрано.")
    notify_many(
        closed,
        Notification.Type.RESPONSE_CLOSED,
        "Набір волонтерів закрито",
        f"На запит «{help_request.title}» вже набрано потрібну кількість волонтерів. "
        "Дякуємо за готовність допомогти!",
        help_request,
    )


@transaction.atomic
def accept(response, recipient):
    help_request, response = _lock_response(response)
    if help_request.recipient_id != recipient.pk:
        raise TransitionError("Це не ваш запит.")
    if help_request.status != Status.ACTIVE:
        raise TransitionError("Набір волонтерів на цей запит уже закрито.")
    if response.status != RStatus.PENDING:
        raise TransitionError("Цей відгук уже розглянуто.")

    _set_response_status(response, RStatus.ACCEPTED)
    notify(
        response.volunteer,
        Notification.Type.REQUEST_ACCEPTED,
        "Вас прийнято як волонтера",
        f"Отримувач прийняв вашу допомогу із запитом «{help_request.title}».",
        help_request,
    )

    accepted = help_request.accepted_responses().count()
    if accepted >= help_request.volunteers_needed:
        _start_work(help_request)
    return accepted


@transaction.atomic
def reject(response, recipient):
    help_request, response = _lock_response(response)
    if help_request.recipient_id != recipient.pk:
        raise TransitionError("Це не ваш запит.")
    if response.status != RStatus.PENDING:
        raise TransitionError("Цей відгук уже розглянуто.")

    _set_response_status(response, RStatus.REJECTED)
    notify(
        response.volunteer,
        Notification.Type.REQUEST_REJECTED,
        "Ваш відгук не прийнято",
        f"Отримувач обрав інших волонтерів для запиту «{help_request.title}».",
        help_request,
    )


def _reopen_if_short(help_request):
    """Back to recruiting when fewer volunteers remain than needed."""
    if (
        help_request.status in (Status.IN_PROGRESS, Status.AWAITING_CONFIRMATION)
        and help_request.accepted_responses().count() < help_request.volunteers_needed
    ):
        _set_status(help_request, Status.ACTIVE)
        return True
    return False


@transaction.atomic
def withdraw(response, volunteer, reason=""):
    """A volunteer leaves a request they responded to (pending or accepted)."""
    help_request, response = _lock_response(response)
    if response.volunteer_id != volunteer.pk:
        raise TransitionError("Це не ваш відгук.")
    if response.status == RStatus.ACCEPTED:
        if not help_request.is_open:
            raise TransitionError("Запит уже закрито.")
        if response.done_at:
            raise TransitionError("Ви вже позначили допомогу виконаною.")
        if not reason.strip():
            raise TransitionError("Вкажіть причину — отримувач на вас розраховує.")
    elif response.status != RStatus.PENDING:
        raise TransitionError("Цей відгук уже неактивний.")

    was_accepted = response.status == RStatus.ACCEPTED
    _set_response_status(response, RStatus.WITHDRAWN, reason)
    if not was_accepted:
        return

    reopened = _reopen_if_short(help_request)
    message = f"{_name(volunteer)} більше не може допомогти із запитом «{help_request.title}»."
    if reason:
        message += f" Причина: {reason}"
    if reopened:
        message += " Запит знову відкрито для волонтерів."
    notify(
        help_request.recipient,
        Notification.Type.VOLUNTEER_WITHDREW,
        "Волонтер вийшов із запиту",
        message,
        help_request,
    )


@transaction.atomic
def remove(response, recipient, reason=""):
    """The recipient removes an accepted volunteer (e.g. they did not show up)."""
    help_request, response = _lock_response(response)
    if help_request.recipient_id != recipient.pk:
        raise TransitionError("Це не ваш запит.")
    if response.status != RStatus.ACCEPTED or not help_request.is_open:
        raise TransitionError("Зняти можна лише прийнятого волонтера у відкритому запиті.")
    if not reason.strip():
        raise TransitionError("Вкажіть причину, щоб волонтер розумів, що сталося.")

    _set_response_status(response, RStatus.REMOVED, reason)
    response.done_at = None
    response.save(update_fields=["done_at"])
    reopened = _reopen_if_short(help_request)
    notify(
        response.volunteer,
        Notification.Type.VOLUNTEER_REMOVED,
        "Вас знято із запиту",
        f"Отримувач зняв вас із запиту «{help_request.title}». Причина: {reason}",
        help_request,
    )
    return reopened


@transaction.atomic
def remove_by_moderator(response, reason):
    """Take a volunteer off an open request, e.g. after their verification was revoked."""
    help_request, response = _lock_response(response)
    if response.status not in (RStatus.ACCEPTED, RStatus.PENDING) or not help_request.is_open:
        return False
    was_accepted = response.status == RStatus.ACCEPTED
    _set_response_status(response, RStatus.REMOVED, reason)
    if not was_accepted:
        return True
    reopened = _reopen_if_short(help_request)
    notify(
        help_request.recipient,
        Notification.Type.VOLUNTEER_WITHDREW,
        "Волонтера знято модератором",
        f"Модератор зняв волонтера із запиту «{help_request.title}»."
        + (" Запит знову відкрито для волонтерів." if reopened else ""),
        help_request,
    )
    return True


# ---------------------------------------------------------------------------
# Finishing
# ---------------------------------------------------------------------------


@transaction.atomic
def mark_done(response, volunteer):
    """An accepted volunteer reports their part as done."""
    help_request, response = _lock_response(response)
    if response.volunteer_id != volunteer.pk or response.status != RStatus.ACCEPTED:
        raise TransitionError("Позначити виконаним може лише прийнятий волонтер.")
    if help_request.status != Status.IN_PROGRESS:
        raise TransitionError("Запит зараз не виконується.")
    if response.done_at:
        raise TransitionError("Ви вже позначили допомогу виконаною.")

    response.done_at = timezone.now()
    response.save(update_fields=["done_at"])

    all_done = not help_request.accepted_responses().filter(done_at__isnull=True).exists()
    if all_done:
        _set_status(help_request, Status.AWAITING_CONFIRMATION)
    notify(
        help_request.recipient,
        Notification.Type.MARKED_DONE,
        "Волонтер позначив допомогу виконаною",
        f"{_name(volunteer)} позначив(ла) запит «{help_request.title}» виконаним. "
        + (
            "Підтвердьте завершення або повідомте, якщо щось не так. "
            "Без відповіді запит завершиться автоматично через 72 години."
            if all_done
            else "Чекаємо на інших волонтерів."
        ),
        help_request,
    )


def _complete(help_request):
    _set_status(help_request, Status.COMPLETED)
    notify_many(
        [help_request.recipient, *_accepted_volunteers(help_request)],
        Notification.Type.REQUEST_COMPLETED,
        "Запит виконано",
        f"Запит «{help_request.title}» завершено. Дякуємо! Залиште оцінку — це допомагає іншим.",
        help_request,
    )


@transaction.atomic
def confirm_completion(help_request, recipient):
    help_request = _lock(help_request)
    if help_request.recipient_id != recipient.pk:
        raise TransitionError("Це не ваш запит.")
    if help_request.status not in (Status.IN_PROGRESS, Status.AWAITING_CONFIRMATION):
        raise TransitionError("Підтвердити можна лише запит, який виконується.")
    _complete(help_request)


@transaction.atomic
def dispute_completion(help_request, recipient, reason=""):
    """The recipient says the help has not actually happened yet."""
    help_request = _lock(help_request)
    if help_request.recipient_id != recipient.pk:
        raise TransitionError("Це не ваш запит.")
    if help_request.status != Status.AWAITING_CONFIRMATION:
        raise TransitionError("Запит не очікує підтвердження.")

    help_request.accepted_responses().update(done_at=None)
    _set_status(help_request, Status.IN_PROGRESS)
    message = f"Отримувач повідомив, що допомогу із запитом «{help_request.title}» ще не завершено."
    if reason:
        message += f" Коментар: {reason}"
    notify_many(
        _accepted_volunteers(help_request),
        Notification.Type.COMPLETION_DISPUTED,
        "Виконання не підтверджено",
        message,
        help_request,
    )


@transaction.atomic
def cancel(help_request, recipient):
    help_request = _lock(help_request)
    if help_request.recipient_id != recipient.pk:
        raise TransitionError("Це не ваш запит.")
    if help_request.status not in CANCELLABLE:
        raise TransitionError("Цей запит не можна скасувати.")

    accepted = _accepted_volunteers(help_request)
    _set_status(help_request, Status.CANCELLED)
    closed = _close_pending(help_request, "Отримувач скасував запит.")
    notify_many(
        [*accepted, *closed],
        Notification.Type.REQUEST_CANCELLED,
        "Запит скасовано",
        f"Отримувач скасував запит «{help_request.title}». Дякуємо за готовність допомогти!",
        help_request,
    )


@transaction.atomic
def cancel_by_moderator(help_request, reason):
    """Staff closes a request (fraud, unsafe, duplicate) and tells everyone why."""
    help_request = _lock(help_request)
    if help_request.status not in CANCELLABLE:
        raise TransitionError("Цей запит уже закрито.")

    accepted = _accepted_volunteers(help_request)
    _set_status(help_request, Status.CANCELLED)
    closed = _close_pending(help_request, "Запит закрито модератором.")
    notify_many(
        [help_request.recipient, *accepted, *closed],
        Notification.Type.REQUEST_CANCELLED,
        "Запит закрито модератором",
        f"Запит «{help_request.title}» закрито модератором. Причина: {reason}",
        help_request,
    )


# ---------------------------------------------------------------------------
# Periodic tasks (called by the cron endpoint, see ADR 0004)
# ---------------------------------------------------------------------------


def _expire(help_request, now):
    accepted = _accepted_volunteers(help_request)
    _set_status(help_request, Status.EXPIRED, now)
    closed = _close_pending(help_request, "Час запиту минув.")
    notify(
        help_request.recipient,
        Notification.Type.REQUEST_EXPIRED,
        "Запит прострочено",
        f"Час запиту «{help_request.title}» минув. За потреби створіть новий.",
        help_request,
    )
    notify_many(
        [*accepted, *closed],
        Notification.Type.REQUEST_EXPIRED,
        "Запит прострочено",
        f"Запит «{help_request.title}» закрито, бо його час минув.",
        help_request,
    )


def expire_overdue(now=None):
    """
    Active requests whose time has come without a full team, and in-progress
    requests nobody finished a week after they should have ended.
    """
    now = now or timezone.now()
    expired = 0
    stale_active = HelpRequest.objects.filter(
        status__in=[Status.ACTIVE, Status.PENDING_MODERATION], needed_date__lt=now
    )
    stale_work = HelpRequest.objects.filter(
        status=Status.IN_PROGRESS,
        needed_date__lt=now - EXPIRE_IN_PROGRESS_AFTER_END,
    )
    for candidate in [*stale_active, *stale_work]:
        with transaction.atomic():
            help_request = _lock(candidate)
            is_stale = (
                help_request.status in (Status.ACTIVE, Status.PENDING_MODERATION)
                and help_request.needed_date < now
            ) or (
                help_request.status == Status.IN_PROGRESS
                and help_request.ends_at + EXPIRE_IN_PROGRESS_AFTER_END < now
            )
            if is_stale:
                _expire(help_request, now)
                expired += 1
    return expired


def auto_confirm(now=None):
    """Complete requests the recipient left unconfirmed for 72 hours."""
    now = now or timezone.now()
    completed = 0
    due = HelpRequest.objects.filter(
        status=Status.AWAITING_CONFIRMATION,
        status_changed_at__lt=now - AUTO_CONFIRM_AFTER,
    )
    for candidate in due:
        with transaction.atomic():
            help_request = _lock(candidate)
            if help_request.status == Status.AWAITING_CONFIRMATION:
                _complete(help_request)
                completed += 1
    return completed


def send_reminders(now=None):
    """One nudge to both sides a day after the help should have ended."""
    now = now or timezone.now()
    sent = 0
    candidates = HelpRequest.objects.filter(
        status=Status.IN_PROGRESS,
        reminder_sent_at__isnull=True,
        needed_date__lt=now - REMIND_AFTER_END,
    ).select_related("recipient")
    for help_request in candidates:
        if help_request.ends_at + REMIND_AFTER_END > now:
            continue
        notify(
            help_request.recipient,
            Notification.Type.REMINDER,
            "Як пройшла допомога?",
            f"Якщо допомогу із запитом «{help_request.title}» надано — підтвердьте завершення. "
            "Якщо волонтер не прийшов — зніміть його, і запит знову стане відкритим.",
            help_request,
        )
        pending_volunteers = [
            r.volunteer
            for r in help_request.accepted_responses()
            .filter(done_at__isnull=True)
            .select_related("volunteer")
        ]
        notify_many(
            pending_volunteers,
            Notification.Type.REMINDER,
            "Не забудьте позначити виконання",
            f"Якщо ви вже допомогли із запитом «{help_request.title}» — позначте це. "
            "Якщо не вийшло — вийдіть із запиту, щоб отримувач знайшов заміну.",
            help_request,
        )
        help_request.reminder_sent_at = now
        help_request.save(update_fields=["reminder_sent_at"])
        sent += 1
    return sent
