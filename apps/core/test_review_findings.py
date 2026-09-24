"""
Regression tests for the security & correctness review (September 2026).
Each test reproduces a scenario found by the review and asserts the fix.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.deletion import delete_account
from apps.conversations import services as chat
from apps.conversations.models import Conversation
from apps.moderation import services as moderation
from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.requests import services
from apps.requests.models import HelpRequest, Response
from apps.requests.services import TransitionError
from conftest import (
    HelpRequestFactory,
    RecipientFactory,
    ResponseFactory,
    ReviewFactory,
    VolunteerFactory,
)

pytestmark = pytest.mark.django_db
Status = HelpRequest.Status


def accepted(help_request, **kwargs):
    return ResponseFactory(help_request=help_request, status=Response.Status.ACCEPTED, **kwargs)


class TestReportPage:
    def test_cannot_read_foreign_message_through_report_page(self, client, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        services.accept(ResponseFactory(help_request=help_request, volunteer=volunteer), recipient)
        message = chat.send(
            Conversation.objects.get(help_request=help_request), volunteer, "+380501234567"
        )
        client.force_login(VolunteerFactory())

        assert client.get(f"/moderation/report/message/{message.pk}/").status_code == 404

    def test_participant_can_report_and_page_shows_no_text(self, client, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        services.accept(ResponseFactory(help_request=help_request, volunteer=volunteer), recipient)
        message = chat.send(
            Conversation.objects.get(help_request=help_request), volunteer, "секрет"
        )
        client.force_login(recipient)

        body = client.get(f"/moderation/report/message/{message.pk}/").content.decode()

        assert "секрет" not in body
        assert "Повідомлення в розмові" in body

    def test_unpublished_review_cannot_be_probed(self, client):
        review = ReviewFactory(published_at=None)
        client.force_login(VolunteerFactory())
        assert client.get(f"/moderation/report/review/{review.pk}/").status_code == 404

    def test_stranger_profile_cannot_be_probed(self, client):
        client.force_login(VolunteerFactory())
        assert client.get(f"/moderation/report/user/{RecipientFactory().pk}/").status_code == 404

    @pytest.mark.parametrize("next_url", ["https://evil.example/", "javascript:alert(1)"])
    def test_next_is_not_an_open_redirect(self, client, help_request, next_url):
        client.force_login(VolunteerFactory())
        url = f"/moderation/report/request/{help_request.pk}/"

        body = client.get(url, {"next": next_url}).content.decode()
        page = client.post(url, {"reason": "spam", "next": next_url})

        assert next_url not in body
        assert page["Location"] == "/"


class TestDemoSafety:
    def test_registration_closed_in_demo_mode(self, client, settings):
        settings.DEMO_MODE = True
        assert client.get("/accounts/register/")["Location"] == "/accounts/login/"

    def test_moderator_cannot_block_demo_accounts(self):
        demo = VolunteerFactory(is_demo=True)
        report = moderation.file_report(RecipientFactory(), demo, Report.Reason.SPAM)

        with pytest.raises(moderation.ModerationError):
            moderation.act_on_report(report, VolunteerFactory())

        demo.refresh_from_db()
        assert demo.is_active


class TestMapPrivacy:
    def test_offset_cannot_be_undone_with_public_id(self, client, help_request):
        from apps.requests.utils import offset_coordinates

        point = client.get("/requests/map/data/").json()[0]
        guessed = offset_coordinates(
            help_request.latitude, help_request.longitude, offset_meters=150, seed=help_request.pk
        )

        assert (point["lat"], point["lon"]) != guessed


class TestLifecycleEdges:
    def test_removing_no_show_after_the_date_keeps_the_remaining_team(self, recipient):
        help_request = HelpRequestFactory(
            recipient=recipient,
            volunteers_needed=2,
            status=Status.IN_PROGRESS,
            needed_date=timezone.now() - timedelta(hours=3),
        )
        accepted(help_request, done_at=timezone.now())
        no_show = accepted(help_request)

        services.remove(no_show, recipient, "Не прийшов")

        help_request.refresh_from_db()
        assert help_request.status == Status.AWAITING_CONFIRMATION
        services.confirm_completion(help_request, recipient)  # no longer blocked

    def test_partial_team_starts_work_instead_of_expiring(self, recipient):
        help_request = HelpRequestFactory(
            recipient=recipient,
            volunteers_needed=2,
            needed_date=timezone.now() - timedelta(hours=1),
        )
        accepted(help_request)

        services.expire_overdue()

        help_request.refresh_from_db()
        assert help_request.status == Status.IN_PROGRESS

    def test_switching_to_home_visit_is_locked_and_accept_rechecks_trust(self, recipient):
        help_request = HelpRequestFactory(recipient=recipient)
        response = ResponseFactory(help_request=help_request, volunteer=VolunteerFactory())

        assert services.editable_fields_error(help_request, ["help_format"], 1)

        HelpRequest.objects.filter(pk=help_request.pk).update(
            help_format=HelpRequest.HelpFormat.HOME_VISIT
        )
        with pytest.raises(TransitionError):
            services.accept(response, recipient)

    def test_content_edit_of_new_recipient_goes_back_to_moderation(self, recipient):
        help_request = HelpRequestFactory(recipient=recipient)  # the only published request

        services.after_edit(help_request, ["description"])

        help_request.refresh_from_db()
        assert help_request.status == Status.PENDING_MODERATION

    def test_verified_recipient_edits_without_review(self):
        help_request = HelpRequestFactory(recipient=RecipientFactory(is_verified=True))
        services.after_edit(help_request, ["description"])
        help_request.refresh_from_db()
        assert help_request.status == Status.ACTIVE


class TestProfilesAndDeletion:
    def test_pending_volunteer_cannot_open_recipient_profile(self, client, recipient, volunteer):
        ResponseFactory(help_request=HelpRequestFactory(recipient=recipient), volunteer=volunteer)
        client.force_login(volunteer)
        assert client.get(f"/accounts/users/{recipient.pk}/").status_code == 404

    def test_deleted_name_disappears_from_other_peoples_notifications(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        services.respond(help_request, volunteer, "Допоможу")
        name = volunteer.get_full_name()
        assert Notification.objects.filter(user=recipient, title__contains=name).exists()

        delete_account(volunteer)

        assert not Notification.objects.filter(title__contains=name).exists()
        assert not Notification.objects.filter(message__contains=name).exists()


class TestCityFilter:
    def test_filter_cannot_probe_private_address(self, client):
        HelpRequestFactory(city="Київ", address="вул. Секретна, 13, кв. 7")

        by_street = client.get("/requests/", {"city": "Секретна"}).context["requests"]
        # (case-insensitive Cyrillic matching needs PostgreSQL; SQLite tests use exact case)
        by_city = client.get("/requests/", {"city": "Київ"}).context["requests"]

        assert len(by_street) == 0
        assert len(by_city) == 1
