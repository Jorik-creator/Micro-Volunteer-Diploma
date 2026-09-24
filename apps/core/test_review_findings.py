"""
Regression tests for the security & correctness review and the QA pass
(September 2026). Each test reproduces a scenario found and asserts the fix.
"""

from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.core import mail
from django.utils import timezone

from apps.accounts.deletion import delete_account
from apps.accounts.permissions import MODERATORS_GROUP
from apps.conversations import services as chat
from apps.conversations.models import Conversation
from apps.moderation import services as moderation
from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.requests import services
from apps.requests.models import Category, HelpRequest, Response
from apps.requests.services import TransitionError
from apps.reviews import services as review_services
from apps.reviews.models import Review
from conftest import (
    CategoryFactory,
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
        name, full_name = volunteer.short_name, volunteer.get_full_name()
        assert Notification.objects.filter(user=recipient, title__contains=name).exists()
        # Older notifications carried the full name
        Notification.objects.create(user=recipient, type="reminder", title=full_name, message="-")

        delete_account(volunteer)

        for gone in (name, full_name):
            assert not Notification.objects.filter(title__contains=gone).exists()
            assert not Notification.objects.filter(message__contains=gone).exists()


class TestCityFilter:
    def test_filter_cannot_probe_private_address(self, client):
        HelpRequestFactory(city="Київ", address="вул. Секретна, 13, кв. 7")

        by_street = client.get("/requests/", {"city": "Секретна"}).context["requests"]
        # (case-insensitive Cyrillic matching needs PostgreSQL; SQLite tests use exact case)
        by_city = client.get("/requests/", {"city": "Київ"}).context["requests"]

        assert len(by_street) == 0
        assert len(by_city) == 1


# ---------------------------------------------------------------------------
# QA pass (September 2026)
# ---------------------------------------------------------------------------


def _flash(page):
    return [str(m) for m in get_messages(page.wsgi_request)]


def _moderator():
    user = VolunteerFactory()
    user.groups.add(Group.objects.get(name=MODERATORS_GROUP))
    return user


def _request_form(**overrides):
    when = timezone.localtime(timezone.now() + timedelta(days=3))
    data = {
        "title": "Купити ліки",
        "description": "Потрібно забрати ліки в аптеці.",
        "category": CategoryFactory().pk,
        "help_format": HelpRequest.HelpFormat.DOORSTEP,
        "urgency": HelpRequest.Urgency.MEDIUM,
        "needed_date": when.strftime("%Y-%m-%dT%H:%M"),
        "duration": HelpRequest.Duration.ONE_HOUR,
        "volunteers_needed": 1,
        "city": "Київ",
        "address": "Київ, вул. Хрещатик, 1",
        "latitude": 50.4501,
        "longitude": 30.5234,
    }
    data.update(overrides)
    return data


class TestMapData:
    def test_times_are_local_and_format_and_city_included(self, client):
        needed = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)  # 12:00 in Kyiv (UTC+2)
        HelpRequestFactory(needed_date=needed, city="Київ")

        point = client.get("/requests/map/data/").json()[0]

        assert point["needed_date"] == "01.12.2026 12:00"
        assert point["help_format"] == HelpRequest.HelpFormat.DOORSTEP
        assert point["help_format_display"] == "Під двері"
        assert point["city"] == "Київ"


class TestBlockingClosesOpenWork:
    def test_blocked_recipient_requests_are_cancelled(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        response = ResponseFactory(help_request=help_request, volunteer=volunteer)
        report = moderation.file_report(volunteer, recipient, Report.Reason.SPAM)

        moderation.act_on_report(report, _moderator())

        help_request.refresh_from_db()
        response.refresh_from_db()
        assert help_request.status == Status.CANCELLED
        assert response.status == Response.Status.CLOSED
        assert Notification.objects.filter(
            user=volunteer, type=Notification.Type.REQUEST_CANCELLED
        ).exists()

    def test_blocked_volunteer_leaves_accepted_request(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        response = ResponseFactory(help_request=help_request, volunteer=volunteer)
        services.accept(response, recipient)
        report = moderation.file_report(recipient, volunteer, Report.Reason.SPAM)

        moderation.act_on_report(report, _moderator())

        help_request.refresh_from_db()
        response.refresh_from_db()
        assert response.status == Response.Status.WITHDRAWN
        assert help_request.status == Status.ACTIVE
        assert Notification.objects.filter(
            user=recipient, type=Notification.Type.VOLUNTEER_WITHDREW
        ).exists()


class TestStats:
    def test_moderator_sees_dashboard_with_published_reviews_only(self, client):
        ReviewFactory()
        ReviewFactory(published_at=None)
        client.force_login(_moderator())

        page = client.get("/stats/dashboard/")

        assert page.status_code == 200
        assert page.context["total_reviews"] == 1
        summary = page.context["status_summary"]
        assert [row[0] for row in summary] == HelpRequest.Status.values
        assert {row[3] for row in summary} <= {
            "muted",
            "warning",
            "danger",
            "blue",
            "navy",
            "success",
        }
        assert client.get("/stats/data/").status_code == 200


class TestReviewMessages:
    def test_second_review_says_both_are_published(self, client, recipient, volunteer):
        done = HelpRequestFactory(
            recipient=recipient, status=Status.COMPLETED, completed_at=timezone.now()
        )
        ResponseFactory(help_request=done, volunteer=volunteer, status=Response.Status.ACCEPTED)
        review_services.submit_review(volunteer, done, recipient, 5)
        client.force_login(recipient)

        page = client.post(f"/reviews/create/{done.pk}/{volunteer.pk}/", {"rating": "5"})

        assert _flash(page) == ["Дякуємо! Оцінки обох сторін опубліковано."]

    def test_rated_first_is_a_review_reminder(self, recipient, volunteer):
        done = HelpRequestFactory(
            recipient=recipient, status=Status.COMPLETED, completed_at=timezone.now()
        )
        ResponseFactory(help_request=done, volunteer=volunteer, status=Response.Status.ACCEPTED)

        review_services.submit_review(volunteer, done, recipient, 5)

        assert Notification.objects.get(user=recipient).type == Notification.Type.REVIEW_REMINDER


class TestRequestStatusJson:
    def test_moderator_sees_any_request(self, client):
        closed = HelpRequestFactory(status=Status.CANCELLED)
        client.force_login(VolunteerFactory())
        assert client.get(f"/requests/{closed.pk}/status/").status_code == 404

        client.force_login(_moderator())
        assert client.get(f"/requests/{closed.pk}/status/").json()["status"] == "cancelled"


class TestRejectedRequests:
    def test_owner_edits_rejected_request_back_into_moderation(self, client, recipient):
        rejected = HelpRequestFactory(
            recipient=recipient, status=Status.REJECTED, moderation_note="Уточніть адресу"
        )
        client.force_login(recipient)

        detail = client.get(f"/requests/{rejected.pk}/")
        page = client.post(f"/requests/{rejected.pk}/edit/", _request_form())

        assert detail.context["can_edit"] and detail.context["can_cancel"]
        assert page.status_code == 302
        rejected.refresh_from_db()
        assert rejected.status == Status.PENDING_MODERATION
        assert rejected.moderation_note == "Уточніть адресу"

    def test_owner_can_cancel_rejected_request(self, recipient):
        rejected = HelpRequestFactory(recipient=recipient, status=Status.REJECTED)
        services.cancel(rejected, recipient)
        rejected.refresh_from_db()
        assert rejected.status == Status.CANCELLED

    def test_finished_request_has_no_owner_buttons(self, client, recipient):
        done = HelpRequestFactory(recipient=recipient, status=Status.COMPLETED)
        client.force_login(recipient)
        context = client.get(f"/requests/{done.pk}/").context
        assert not context["can_edit"] and not context["can_cancel"]


class TestListFilters:
    def test_help_format_filter(self, client):
        HelpRequestFactory(help_format=HelpRequest.HelpFormat.HOME_VISIT)
        remote = HelpRequestFactory(help_format=HelpRequest.HelpFormat.REMOTE)

        found = client.get("/requests/", {"help_format": "remote"}).context["requests"]

        assert list(found) == [remote]

    def test_can_take_hides_home_visits_from_unverified_volunteer(self, client, volunteer):
        HelpRequestFactory(help_format=HelpRequest.HelpFormat.HOME_VISIT)
        ResponseFactory(volunteer=volunteer)  # already responded: cannot take it again
        doorstep = HelpRequestFactory(help_format=HelpRequest.HelpFormat.DOORSTEP)
        client.force_login(volunteer)

        page = client.get("/requests/", {"can_take": "on"})

        assert list(page.context["requests"]) == [doorstep]
        assert page.context["volunteer_can_take_home_visits"] is False


class TestHonestPublishCopy:
    def test_message_counts_notified_volunteers(self, client):
        VolunteerFactory(is_verified=True, latitude=50.4502, longitude=30.5235)
        client.force_login(RecipientFactory(is_verified=True))

        page = client.post("/requests/create/", _request_form())

        assert _flash(page) == ["Запит опубліковано. Сповіщення надіслано 1 волонтеру поруч."]

    def test_message_without_nearby_volunteers(self, client):
        client.force_login(RecipientFactory(is_verified=True))

        page = client.post("/requests/create/", _request_form())

        assert _flash(page) == ["Запит опубліковано. Волонтери побачать його у списку й на карті."]


class TestReasonErrors:
    def test_too_long_reason_is_reported_as_such(self, client, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        response = ResponseFactory(help_request=help_request, volunteer=volunteer)
        services.accept(response, recipient)
        client.force_login(volunteer)

        page = client.post(f"/requests/{help_request.pk}/withdraw/", {"reason": "x" * 301})

        assert _flash(page) == ["Причина задовга — не більше 300 символів."]
        response.refresh_from_db()
        assert response.status == Response.Status.ACCEPTED


class TestNotificationLinks:
    def test_message_notification_opens_conversation_and_email_has_link(
        self, recipient, volunteer, django_capture_on_commit_callbacks
    ):
        help_request = HelpRequestFactory(recipient=recipient)
        services.accept(ResponseFactory(help_request=help_request, volunteer=volunteer), recipient)
        conversation = Conversation.objects.get(help_request=help_request)

        with django_capture_on_commit_callbacks(execute=True):
            chat.send(conversation, volunteer, "Буду о 17:00")

        notification = Notification.objects.get(user=recipient, type=Notification.Type.NEW_MESSAGE)
        assert notification.url == f"/conversations/{conversation.pk}/"
        assert f"http://testserver/conversations/{conversation.pk}/" in mail.outbox[-1].body

    def test_accepted_volunteer_is_pointed_to_address_and_chat(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        services.accept(ResponseFactory(help_request=help_request, volunteer=volunteer), recipient)

        notification = Notification.objects.get(
            user=volunteer, type=Notification.Type.REQUEST_ACCEPTED
        )
        assert "адреса й розмова з отримувачем" in notification.message
        assert notification.url == f"/requests/{help_request.pk}/"

    def test_url_falls_back_to_notification_list(self, volunteer):
        notification = Notification.objects.create(
            user=volunteer, type=Notification.Type.VERIFICATION_DECISION, title="t", message="m"
        )
        assert notification.url == "/notifications/"


class TestNeutralWording:
    def test_tag_labels_have_no_gendered_endings(self):
        assert not [label for label in Review.Tag.labels if "(" in label]

    def test_new_response_title(self, recipient, volunteer):
        services.respond(HelpRequestFactory(recipient=recipient), volunteer)
        title = Notification.objects.get(user=recipient).title
        assert title == f"Новий відгук волонтера: {volunteer.short_name}"


class TestExpiredInModeration:
    def test_recipient_is_told_the_moderator_did_not_make_it(self, recipient):
        HelpRequestFactory(
            recipient=recipient,
            status=Status.PENDING_MODERATION,
            needed_date=timezone.now() - timedelta(hours=1),
        )

        services.expire_overdue()

        message = Notification.objects.get(user=recipient).message
        assert "Модератор не встиг перевірити запит" in message


class TestConversationWindow:
    def test_volunteer_leaving_an_old_open_request_keeps_chat_readable(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient, volunteers_needed=2)
        response = ResponseFactory(help_request=help_request, volunteer=volunteer)
        services.accept(response, recipient)
        HelpRequest.objects.filter(pk=help_request.pk).update(
            status_changed_at=timezone.now() - timedelta(days=30)
        )

        services.withdraw(response, volunteer, "Захворів")

        conversation = Conversation.objects.get(help_request=help_request)
        response.refresh_from_db()
        assert conversation.closed_since == response.status_changed_at
        assert not conversation.is_archived

    def test_archived_conversation_is_not_counted_as_unread(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        services.accept(ResponseFactory(help_request=help_request, volunteer=volunteer), recipient)
        assert chat.unread_count(recipient) == 1  # the system greeting

        HelpRequest.objects.filter(pk=help_request.pk).update(
            status=Status.COMPLETED, status_changed_at=timezone.now() - timedelta(days=30)
        )

        assert chat.unread_count(recipient) == 0


class TestCategoryIcons:
    def test_migration_sets_paw_for_animals(self):
        Category.objects.create(name="Тварини", slug="tvaryny", icon="bi-piggy-bank")
        migration = import_module("apps.requests.migrations.0009_category_icons")

        migration.set_icons(django_apps, None)

        assert Category.objects.get(slug="tvaryny").icon == "paw"
