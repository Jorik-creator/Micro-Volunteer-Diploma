"""
Tests for the help request lifecycle (apps.requests.services).

Each test walks one transition from docs/ROADMAP.md and checks both the
resulting states and who was notified.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.requests import services
from apps.requests.models import HelpRequest, Response
from apps.requests.services import TransitionError
from conftest import HelpRequestFactory, RecipientFactory, ResponseFactory, VolunteerFactory

pytestmark = pytest.mark.django_db

Status = HelpRequest.Status
RStatus = Response.Status


def notified(user, type):
    return Notification.objects.filter(user=user, type=type).exists()


@pytest.fixture
def team_request(recipient):
    """Active request that needs two volunteers."""
    return HelpRequestFactory(recipient=recipient, volunteers_needed=2)


def accepted(help_request, **kwargs):
    return ResponseFactory(help_request=help_request, status=RStatus.ACCEPTED, **kwargs)


def refresh(*objects):
    for obj in objects:
        obj.refresh_from_db()


# ---------------------------------------------------------------------------
# respond
# ---------------------------------------------------------------------------


class TestRespond:
    def test_creates_pending_response_and_notifies_recipient(self, help_request, volunteer):
        response = services.respond(help_request, volunteer, "Можу завтра")

        assert response.status == RStatus.PENDING
        assert notified(help_request.recipient, Notification.Type.NEW_RESPONSE)

    def test_every_volunteer_response_notifies_recipient(self, help_request):
        """Regression: get_or_create used to swallow the 2nd+ response notification."""
        services.respond(help_request, VolunteerFactory())
        services.respond(help_request, VolunteerFactory())

        assert (
            Notification.objects.filter(
                user=help_request.recipient, type=Notification.Type.NEW_RESPONSE
            ).count()
            == 2
        )

    def test_rejects_non_active_request(self, help_request, volunteer):
        help_request.status = Status.IN_PROGRESS
        help_request.save()

        with pytest.raises(TransitionError):
            services.respond(help_request, volunteer)

    def test_rejects_recipient(self, help_request, recipient):
        with pytest.raises(TransitionError):
            services.respond(help_request, recipient)

    def test_rejects_duplicate(self, help_request, volunteer):
        services.respond(help_request, volunteer)
        with pytest.raises(TransitionError):
            services.respond(help_request, volunteer)

    def test_withdrawn_volunteer_may_respond_again(self, help_request, volunteer):
        response = services.respond(help_request, volunteer)
        services.withdraw(response, volunteer)

        again = services.respond(help_request, volunteer, "Все ж можу")

        assert again.pk == response.pk
        assert again.status == RStatus.PENDING


# ---------------------------------------------------------------------------
# accept / reject
# ---------------------------------------------------------------------------


class TestAccept:
    def test_partial_accept_keeps_request_active(self, team_request, recipient):
        response = ResponseFactory(help_request=team_request)

        assert services.accept(response, recipient) == 1

        refresh(team_request, response)
        assert response.status == RStatus.ACCEPTED
        assert team_request.status == Status.ACTIVE
        assert notified(response.volunteer, Notification.Type.REQUEST_ACCEPTED)

    def test_full_team_starts_work_and_closes_pending(self, team_request, recipient):
        first, second, extra = (ResponseFactory(help_request=team_request) for _ in range(3))

        services.accept(first, recipient)
        services.accept(second, recipient)

        refresh(team_request, extra)
        assert team_request.status == Status.IN_PROGRESS
        assert extra.status == RStatus.CLOSED
        assert notified(extra.volunteer, Notification.Type.RESPONSE_CLOSED)

    def test_accept_on_closed_request_is_transition_error_not_500(self, help_request, recipient):
        """Regression: used to raise DoesNotExist (HTTP 500)."""
        response = ResponseFactory(help_request=help_request)
        help_request.status = Status.CANCELLED
        help_request.save()

        with pytest.raises(TransitionError):
            services.accept(response, recipient)

    def test_only_owner_can_accept(self, help_request):
        response = ResponseFactory(help_request=help_request)

        with pytest.raises(TransitionError):
            services.accept(response, RecipientFactory())

    def test_view_shows_error_instead_of_crashing(self, client_logged_in_recipient, help_request):
        response = ResponseFactory(help_request=help_request)
        help_request.status = Status.EXPIRED
        help_request.save()

        page = client_logged_in_recipient.post(f"/requests/responses/{response.pk}/accept/")

        assert page.status_code == 302

    def test_reject_notifies_volunteer(self, help_request, recipient):
        response = ResponseFactory(help_request=help_request)

        services.reject(response, recipient)

        refresh(response)
        assert response.status == RStatus.REJECTED
        assert notified(response.volunteer, Notification.Type.REQUEST_REJECTED)


# ---------------------------------------------------------------------------
# withdraw / remove
# ---------------------------------------------------------------------------


class TestWithdrawAndRemove:
    def test_pending_volunteer_withdraws_silently(self, help_request, volunteer):
        response = ResponseFactory(help_request=help_request, volunteer=volunteer)

        services.withdraw(response, volunteer)

        refresh(response)
        assert response.status == RStatus.WITHDRAWN
        assert not notified(help_request.recipient, Notification.Type.VOLUNTEER_WITHDREW)

    def test_accepted_volunteer_needs_reason(self, help_request, volunteer):
        response = accepted(help_request, volunteer=volunteer)
        help_request.status = Status.IN_PROGRESS
        help_request.save()

        with pytest.raises(TransitionError):
            services.withdraw(response, volunteer, "  ")

    def test_accepted_withdrawal_reopens_request(self, help_request, volunteer):
        response = accepted(help_request, volunteer=volunteer)
        help_request.status = Status.IN_PROGRESS
        help_request.save()

        services.withdraw(response, volunteer, "Захворів")

        refresh(help_request, response)
        assert response.status == RStatus.WITHDRAWN
        assert response.status_reason == "Захворів"
        assert help_request.status == Status.ACTIVE
        assert notified(help_request.recipient, Notification.Type.VOLUNTEER_WITHDREW)

    def test_withdrawal_after_marking_done_is_blocked(self, help_request, volunteer):
        response = accepted(help_request, volunteer=volunteer, done_at=timezone.now())
        help_request.status = Status.AWAITING_CONFIRMATION
        help_request.save()

        with pytest.raises(TransitionError):
            services.withdraw(response, volunteer, "Передумав")

    def test_cannot_withdraw_someone_else(self, help_request, volunteer):
        response = ResponseFactory(help_request=help_request)

        with pytest.raises(TransitionError):
            services.withdraw(response, volunteer)

    def test_recipient_removes_no_show_volunteer(self, help_request, recipient):
        response = accepted(help_request)
        help_request.status = Status.IN_PROGRESS
        help_request.save()

        reopened = services.remove(response, recipient, "Не прийшов")

        refresh(help_request, response)
        assert reopened is True
        assert response.status == RStatus.REMOVED
        assert help_request.status == Status.ACTIVE
        assert notified(response.volunteer, Notification.Type.VOLUNTEER_REMOVED)

    def test_remove_requires_reason(self, help_request, recipient):
        response = accepted(help_request)
        with pytest.raises(TransitionError):
            services.remove(response, recipient, "")

    def test_removing_one_of_surplus_keeps_work_going(self, recipient):
        help_request = HelpRequestFactory(
            recipient=recipient, volunteers_needed=1, status=Status.IN_PROGRESS
        )
        first, _second = accepted(help_request), accepted(help_request)

        assert services.remove(first, recipient, "Досить одного") is False

        refresh(help_request)
        assert help_request.status == Status.IN_PROGRESS


# ---------------------------------------------------------------------------
# completion
# ---------------------------------------------------------------------------


class TestCompletion:
    def test_waits_for_every_accepted_volunteer(self, team_request):
        first, second = accepted(team_request), accepted(team_request)
        team_request.status = Status.IN_PROGRESS
        team_request.save()

        services.mark_done(first, first.volunteer)
        refresh(team_request)
        assert team_request.status == Status.IN_PROGRESS

        services.mark_done(second, second.volunteer)
        refresh(team_request)
        assert team_request.status == Status.AWAITING_CONFIRMATION
        assert notified(team_request.recipient, Notification.Type.MARKED_DONE)

    def test_mark_done_twice_is_rejected(self, help_request):
        response = accepted(help_request)
        help_request.status = Status.IN_PROGRESS
        help_request.save()
        services.mark_done(response, response.volunteer)

        with pytest.raises(TransitionError):
            services.mark_done(response, response.volunteer)

    def test_recipient_confirms_and_everyone_is_thanked(self, team_request, recipient):
        first, second = accepted(team_request), accepted(team_request)
        team_request.status = Status.AWAITING_CONFIRMATION
        team_request.save()

        services.confirm_completion(team_request, recipient)

        refresh(team_request)
        assert team_request.status == Status.COMPLETED
        assert team_request.completed_at is not None
        for user in (recipient, first.volunteer, second.volunteer):
            assert notified(user, Notification.Type.REQUEST_COMPLETED)

    def test_recipient_may_complete_straight_from_in_progress(self, help_request, recipient):
        accepted(help_request)
        help_request.status = Status.IN_PROGRESS
        help_request.save()

        services.confirm_completion(help_request, recipient)

        refresh(help_request)
        assert help_request.status == Status.COMPLETED

    def test_dispute_returns_to_in_progress_and_clears_done(self, help_request, recipient):
        response = accepted(help_request, done_at=timezone.now())
        help_request.status = Status.AWAITING_CONFIRMATION
        help_request.save()

        services.dispute_completion(help_request, recipient, "Ліки ще не привезли")

        refresh(help_request, response)
        assert help_request.status == Status.IN_PROGRESS
        assert response.done_at is None
        assert notified(response.volunteer, Notification.Type.COMPLETION_DISPUTED)

    def test_volunteer_cannot_confirm(self, help_request, volunteer):
        help_request.status = Status.AWAITING_CONFIRMATION
        help_request.save()

        with pytest.raises(TransitionError):
            services.confirm_completion(help_request, volunteer)


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


class TestCancel:
    def test_closes_pending_and_notifies_all_volunteers(self, team_request, recipient):
        pending = ResponseFactory(help_request=team_request)
        taken = accepted(team_request)

        services.cancel(team_request, recipient)

        refresh(team_request, pending, taken)
        assert team_request.status == Status.CANCELLED
        assert pending.status == RStatus.CLOSED
        assert taken.status == RStatus.ACCEPTED  # stays in the archive
        assert notified(pending.volunteer, Notification.Type.REQUEST_CANCELLED)
        assert notified(taken.volunteer, Notification.Type.REQUEST_CANCELLED)

    def test_cannot_cancel_completed(self, help_request, recipient):
        help_request.status = Status.COMPLETED
        help_request.save()

        with pytest.raises(TransitionError):
            services.cancel(help_request, recipient)


# ---------------------------------------------------------------------------
# editing
# ---------------------------------------------------------------------------


class TestEditing:
    def test_date_is_locked_once_volunteers_responded(self, help_request):
        ResponseFactory(help_request=help_request)

        error = services.editable_fields_error(help_request, ["needed_date"], 1)

        assert error

    def test_description_stays_editable(self, help_request):
        ResponseFactory(help_request=help_request)

        assert services.editable_fields_error(help_request, ["description"], 1) is None

    def test_cannot_need_fewer_than_accepted(self, team_request):
        accepted(team_request)
        accepted(team_request)

        assert services.editable_fields_error(team_request, [], 1)

    def test_lowering_to_accepted_count_starts_work(self, team_request):
        accepted(team_request)
        pending = ResponseFactory(help_request=team_request)
        team_request.volunteers_needed = 1
        team_request.save()

        services.after_edit(team_request)

        refresh(team_request, pending)
        assert team_request.status == Status.IN_PROGRESS
        assert pending.status == RStatus.CLOSED

    def test_edit_view_blocks_date_change_after_response(
        self, client_logged_in_recipient, help_request, category
    ):
        ResponseFactory(help_request=help_request)
        new_date = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")

        page = client_logged_in_recipient.post(
            f"/requests/{help_request.pk}/edit/",
            {
                "title": help_request.title,
                "description": help_request.description,
                "category": category.pk,
                "urgency": help_request.urgency,
                "needed_date": new_date,
                "duration": help_request.duration,
                "volunteers_needed": 1,
                "address": help_request.address,
            },
        )

        assert page.status_code == 200  # form re-rendered with the error
        assert "дату й адресу змінити не можна" in page.content.decode()


# ---------------------------------------------------------------------------
# periodic jobs
# ---------------------------------------------------------------------------


class TestPeriodicJobs:
    def test_expire_closes_pending_and_notifies(self, recipient):
        help_request = HelpRequestFactory(
            recipient=recipient, needed_date=timezone.now() - timedelta(hours=1)
        )
        pending = ResponseFactory(help_request=help_request)

        assert services.expire_overdue() == 1

        refresh(help_request, pending)
        assert help_request.status == Status.EXPIRED
        assert pending.status == RStatus.CLOSED
        assert notified(recipient, Notification.Type.REQUEST_EXPIRED)
        assert notified(pending.volunteer, Notification.Type.REQUEST_EXPIRED)

    def test_stale_in_progress_expires_after_a_week(self):
        now = timezone.now()
        fresh = HelpRequestFactory(status=Status.IN_PROGRESS, needed_date=now - timedelta(days=2))
        stale = HelpRequestFactory(status=Status.IN_PROGRESS, needed_date=now - timedelta(days=8))

        services.expire_overdue(now)

        refresh(fresh, stale)
        assert fresh.status == Status.IN_PROGRESS
        assert stale.status == Status.EXPIRED

    def test_auto_confirm_after_72_hours(self):
        now = timezone.now()
        due = HelpRequestFactory(
            status=Status.AWAITING_CONFIRMATION, status_changed_at=now - timedelta(hours=73)
        )
        recent = HelpRequestFactory(
            status=Status.AWAITING_CONFIRMATION, status_changed_at=now - timedelta(hours=10)
        )

        assert services.auto_confirm(now) == 1

        refresh(due, recent)
        assert due.status == Status.COMPLETED
        assert recent.status == Status.AWAITING_CONFIRMATION

    def test_reminder_sent_once(self, recipient):
        now = timezone.now()
        help_request = HelpRequestFactory(
            recipient=recipient,
            status=Status.IN_PROGRESS,
            needed_date=now - timedelta(days=2),
        )
        response = accepted(help_request)

        assert services.send_reminders(now) == 1
        assert services.send_reminders(now) == 0

        assert notified(recipient, Notification.Type.REMINDER)
        assert notified(response.volunteer, Notification.Type.REMINDER)


class TestUrgencyOrdering:
    def test_critical_before_low_regardless_of_alphabet(self):
        """Regression: order_by('urgency') sorted alphabetically (critical, high, low, medium)."""
        low = HelpRequestFactory(urgency=HelpRequest.Urgency.LOW)
        medium = HelpRequestFactory(urgency=HelpRequest.Urgency.MEDIUM)
        critical = HelpRequestFactory(urgency=HelpRequest.Urgency.CRITICAL)
        high = HelpRequestFactory(urgency=HelpRequest.Urgency.HIGH)

        ordered = list(HelpRequest.objects.ordered_by_urgency())

        assert ordered == [critical, high, medium, low]


# ---------------------------------------------------------------------------
# views wiring (each action renders and redirects)
# ---------------------------------------------------------------------------


class TestActionViews:
    def test_volunteer_withdraws_via_view(
        self, client_logged_in_volunteer, help_request, volunteer
    ):
        response = accepted(help_request, volunteer=volunteer)
        help_request.status = Status.IN_PROGRESS
        help_request.save()

        page = client_logged_in_volunteer.post(
            f"/requests/{help_request.pk}/withdraw/", {"reason": "Не встигаю"}
        )

        assert page.status_code == 302
        refresh(response)
        assert response.status == RStatus.WITHDRAWN

    def test_recipient_removes_via_view(self, client_logged_in_recipient, help_request):
        response = accepted(help_request)

        client_logged_in_recipient.post(
            f"/requests/responses/{response.pk}/remove/", {"reason": "Не прийшов"}
        )

        refresh(response)
        assert response.status == RStatus.REMOVED

    def test_confirm_and_dispute_views(self, client_logged_in_recipient, help_request):
        accepted(help_request, done_at=timezone.now())
        help_request.status = Status.AWAITING_CONFIRMATION
        help_request.save()

        client_logged_in_recipient.post(f"/requests/{help_request.pk}/dispute/", {"reason": "ні"})
        refresh(help_request)
        assert help_request.status == Status.IN_PROGRESS

        client_logged_in_recipient.post(f"/requests/{help_request.pk}/confirm/")
        refresh(help_request)
        assert help_request.status == Status.COMPLETED

    def test_actions_reject_get(self, client_logged_in_recipient, help_request):
        page = client_logged_in_recipient.get(f"/requests/{help_request.pk}/confirm/")
        assert page.status_code == 405

    def test_my_responses_page(self, client_logged_in_volunteer, help_request, volunteer):
        ResponseFactory(help_request=help_request, volunteer=volunteer)

        page = client_logged_in_volunteer.get("/requests/my-responses/")

        assert page.status_code == 200
        assert help_request.title in page.content.decode()

    def test_my_responses_is_volunteer_only(self, client_logged_in_recipient):
        assert client_logged_in_recipient.get("/requests/my-responses/").status_code == 302

    @pytest.mark.parametrize(
        "status",
        [Status.ACTIVE, Status.IN_PROGRESS, Status.AWAITING_CONFIRMATION, Status.COMPLETED],
    )
    def test_detail_renders_for_owner_and_volunteer_in_every_state(
        self, client, help_request, volunteer, recipient, status
    ):
        accepted(help_request, volunteer=volunteer)
        ResponseFactory(help_request=help_request)
        help_request.status = status
        help_request.save()

        for user in (recipient, volunteer):
            client.force_login(user)
            assert client.get(f"/requests/{help_request.pk}/").status_code == 200


class TestModeratorCancel:
    def test_everyone_is_told(self, help_request, recipient):
        taken = accepted(help_request)

        services.cancel_by_moderator(help_request, "шахрайство")

        refresh(help_request)
        assert help_request.status == Status.CANCELLED
        assert notified(recipient, Notification.Type.REQUEST_CANCELLED)
        assert notified(taken.volunteer, Notification.Type.REQUEST_CANCELLED)

    def test_admin_action(self, admin_client, help_request):
        admin_client.post(
            "/admin/requests/helprequest/",
            {"action": "close_as_moderator", "_selected_action": [help_request.pk]},
        )

        refresh(help_request)
        assert help_request.status == Status.CANCELLED
