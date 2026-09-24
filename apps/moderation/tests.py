"""
Tests for trust levels, verification, invite codes, premoderation and reports.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core import mail
from django.utils import timezone

from apps.accounts import emails
from apps.accounts.permissions import MODERATORS_GROUP
from apps.moderation import services
from apps.moderation.models import InviteCode, Report, VerificationRequest
from apps.moderation.services import ModerationError
from apps.notifications.models import Notification
from apps.requests import services as request_services
from apps.requests.models import HelpRequest, Response
from apps.requests.services import TransitionError
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


@pytest.fixture
def moderator():
    user = VolunteerFactory()
    user.groups.add(Group.objects.get(name=MODERATORS_GROUP))
    return user


def new_request(**kwargs):
    """Unsaved request as the create form would build it."""
    return HelpRequest(
        title="Купити ліки",
        description="Потрібно забрати ліки в аптеці",
        category=CategoryFactory(),
        needed_date=timezone.now() + timedelta(days=1),
        address="Київ, Хрещатик 1",
        help_format=HelpRequest.HelpFormat.DOORSTEP,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Trust levels
# ---------------------------------------------------------------------------


class TestTrustLevels:
    def test_levels(self):
        assert VolunteerFactory(email_verified_at=None).trust_level == 0
        assert VolunteerFactory().trust_level == 1
        assert VolunteerFactory(is_verified=True).trust_level == 2

    def test_unconfirmed_volunteer_cannot_respond(self, help_request):
        with pytest.raises(TransitionError, match="email"):
            request_services.respond(help_request, VolunteerFactory(email_verified_at=None))

    def test_home_visit_needs_verified_volunteer(self):
        home = HelpRequestFactory(help_format=HelpRequest.HelpFormat.HOME_VISIT)

        with pytest.raises(TransitionError, match="перевіреним"):
            request_services.respond(home, VolunteerFactory())
        assert request_services.respond(home, VolunteerFactory(is_verified=True))

    def test_detail_page_explains_block(self, client_logged_in_volunteer):
        home = HelpRequestFactory(help_format=HelpRequest.HelpFormat.HOME_VISIT)
        body = client_logged_in_volunteer.get(f"/requests/{home.pk}/").content.decode()
        assert "лише перевіреним волонтерам" in body


class TestPublishing:
    def test_unconfirmed_recipient_gets_a_draft(self):
        recipient = RecipientFactory(email_verified_at=None)

        help_request = request_services.create_request(new_request(), recipient)

        assert help_request.status == Status.DRAFT

    def test_first_requests_are_premoderated(self):
        recipient = RecipientFactory()

        help_request = request_services.create_request(new_request(), recipient)

        assert help_request.status == Status.PENDING_MODERATION

    def test_after_three_published_requests_no_premoderation(self):
        recipient = RecipientFactory()
        HelpRequestFactory.create_batch(3, recipient=recipient, status=Status.COMPLETED)

        help_request = request_services.create_request(new_request(), recipient)

        assert help_request.status == Status.ACTIVE

    def test_verified_recipient_publishes_immediately(self):
        help_request = request_services.create_request(
            new_request(), RecipientFactory(is_verified=True)
        )
        assert help_request.status == Status.ACTIVE
        assert help_request.published_at is not None

    def test_draft_published_after_email_confirmation(self):
        recipient = RecipientFactory(email_verified_at=None)
        draft = request_services.create_request(new_request(), recipient)

        with pytest.raises(TransitionError):
            request_services.publish(draft, recipient)
        recipient.email_verified_at = timezone.now()
        recipient.save()

        assert request_services.publish(draft, recipient) == Status.PENDING_MODERATION

    def test_moderator_approves(self, moderator):
        recipient = RecipientFactory()
        pending = request_services.create_request(new_request(), recipient)

        request_services.approve(pending, moderator)

        pending.refresh_from_db()
        assert pending.status == Status.ACTIVE
        assert Notification.objects.filter(user=recipient, type="request_approved").exists()

    def test_moderator_rejects_with_reason(self, moderator):
        pending = request_services.create_request(new_request(), RecipientFactory())

        with pytest.raises(TransitionError):
            request_services.reject_request(pending, moderator, "")
        request_services.reject_request(pending, moderator, "Схоже на рекламу")

        pending.refresh_from_db()
        assert pending.status == Status.REJECTED
        assert pending.moderation_note == "Схоже на рекламу"

    def test_pending_request_expires(self):
        pending = HelpRequestFactory(
            status=Status.PENDING_MODERATION, needed_date=timezone.now() - timedelta(hours=1)
        )
        request_services.expire_overdue()
        pending.refresh_from_db()
        assert pending.status == Status.EXPIRED

    def test_remote_request_needs_no_address(self, client_logged_in_recipient, category):
        page = client_logged_in_recipient.post(
            "/requests/create/",
            {
                "title": "Допомога з Дією",
                "description": "Не можу подати заявку в застосунку",
                "category": category.pk,
                "help_format": "remote",
                "urgency": "medium",
                "needed_date": (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "duration": "30min",
                "volunteers_needed": 1,
                "address": "",
            },
        )
        assert page.status_code == 302
        created = HelpRequest.objects.get(title="Допомога з Дією")
        assert created.address == "" and created.latitude is None


# ---------------------------------------------------------------------------
# Email confirmation
# ---------------------------------------------------------------------------


class TestEmailConfirmation:
    def test_registration_sends_link(self, client):
        client.post(
            "/accounts/register/",
            {
                "username": "newbie",
                "email": "newbie@example.com",
                "first_name": "Олена",
                "last_name": "Коваль",
                "user_type": "volunteer",
                "password1": "Str0ng-pass-123",
                "password2": "Str0ng-pass-123",
            },
        )
        assert len(mail.outbox) == 1
        assert "/accounts/confirm-email/" in mail.outbox[0].body

    def test_link_confirms(self, client):
        user = VolunteerFactory(email_verified_at=None)

        client.get(f"/accounts/confirm-email/{emails.make_token(user)}/")

        user.refresh_from_db()
        assert user.email_verified_at is not None

    def test_link_for_old_email_is_invalid(self, client):
        user = VolunteerFactory(email_verified_at=None)
        token = emails.make_token(user)
        user.email = "changed@example.com"
        user.save()

        client.get(f"/accounts/confirm-email/{token}/")

        user.refresh_from_db()
        assert user.email_verified_at is None

    def test_register_preselects_role(self, client):
        page = client.get("/accounts/register/?role=volunteer")
        assert page.context["form"].initial["user_type"] == "volunteer"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def application(user):
    return services.apply(user, city="Київ", about="Хочу допомагати літнім людям")


class TestVerification:
    def test_needs_confirmed_email(self):
        with pytest.raises(ModerationError):
            application(VolunteerFactory(email_verified_at=None))

    def test_one_pending_at_a_time(self, volunteer):
        application(volunteer)
        with pytest.raises(ModerationError):
            application(volunteer)

    def test_approve_grants_l2_and_notifies(self, volunteer, moderator):
        services.approve_verification(application(volunteer), moderator)

        volunteer.refresh_from_db()
        assert volunteer.is_verified
        assert Notification.objects.filter(user=volunteer, type="verification").exists()

    def test_reject_requires_reason_and_blocks_reapply_for_a_week(self, volunteer, moderator):
        pending = application(volunteer)
        with pytest.raises(ModerationError):
            services.reject_verification(pending, moderator, " ")
        services.reject_verification(pending, moderator, "Мало інформації")

        assert services.application_error(volunteer)
        later = timezone.now() + timedelta(days=8)
        assert services.application_error(volunteer, now=later) is None

    def test_revoke_takes_volunteer_off_open_requests(self, moderator, recipient):
        volunteer = VolunteerFactory(is_verified=True)
        help_request = HelpRequestFactory(recipient=recipient, status=Status.IN_PROGRESS)
        response = ResponseFactory(
            help_request=help_request, volunteer=volunteer, status=Response.Status.ACCEPTED
        )

        assert services.revoke_verification(volunteer, moderator, "Скарги отримувачів") == 1

        volunteer.refresh_from_db()
        response.refresh_from_db()
        help_request.refresh_from_db()
        assert not volunteer.is_verified
        assert response.status == Response.Status.REMOVED
        assert help_request.status == Status.ACTIVE
        assert volunteer.verification_requests.first().status == "revoked"


class TestInviteCodes:
    def test_redeem_grants_l2(self, volunteer):
        code = InviteCode.objects.create(organization="ГО Добросусідство", max_uses=1)

        assert services.redeem_invite(volunteer, code.code.lower()) == "ГО Добросусідство"

        volunteer.refresh_from_db()
        assert volunteer.is_verified
        assert services.verified_organization(volunteer) == "ГО Добросусідство"

    def test_used_up_code_is_rejected(self, volunteer):
        code = InviteCode.objects.create(organization="ГО", max_uses=1, uses_count=1)
        with pytest.raises(ModerationError):
            services.redeem_invite(volunteer, code.code)

    def test_expired_code_is_rejected(self, volunteer):
        code = InviteCode.objects.create(
            organization="ГО", expires_at=timezone.now() - timedelta(days=1)
        )
        with pytest.raises(ModerationError):
            services.redeem_invite(volunteer, code.code)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class TestReports:
    def test_one_open_report_per_person(self, volunteer, help_request):
        services.file_report(volunteer, help_request, Report.Reason.FRAUD)
        with pytest.raises(ModerationError):
            services.file_report(volunteer, help_request, Report.Reason.SPAM)

    def test_acting_on_request_report_closes_it(self, volunteer, help_request, moderator):
        report = services.file_report(volunteer, help_request, Report.Reason.FRAUD)
        other = services.file_report(VolunteerFactory(), help_request, Report.Reason.UNSAFE)

        services.act_on_report(report, moderator, "Шахрайство підтверджено")

        help_request.refresh_from_db()
        other.refresh_from_db()
        assert help_request.status == Status.CANCELLED
        assert other.status == Report.Status.RESOLVED  # duplicates closed together
        assert Notification.objects.filter(user=volunteer, type="report_resolved").exists()

    def test_acting_on_review_hides_it(self, volunteer, moderator):
        review = ReviewFactory()
        report = services.file_report(volunteer, review, Report.Reason.OFFENSIVE)

        services.act_on_report(report, moderator)

        review.refresh_from_db()
        assert review.hidden_at is not None

    def test_acting_on_user_blocks_account(self, recipient, moderator):
        offender = VolunteerFactory()
        report = services.file_report(recipient, offender, Report.Reason.UNSAFE)

        services.act_on_report(report, moderator)

        offender.refresh_from_db()
        assert not offender.is_active

    def test_dismiss(self, volunteer, help_request, moderator):
        report = services.file_report(volunteer, help_request, Report.Reason.OTHER)

        services.dismiss_report(report, moderator)

        report.refresh_from_db()
        assert report.status == Report.Status.DISMISSED


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class TestViews:
    def test_queue_is_moderators_only(self, client_logged_in_volunteer):
        assert client_logged_in_volunteer.get("/moderation/").status_code == 403

    @pytest.mark.parametrize("tab", ["verification", "requests", "reports"])
    def test_queue_tabs_render(self, client, moderator, volunteer, help_request, tab):
        application(VolunteerFactory())
        HelpRequestFactory(status=Status.PENDING_MODERATION)
        services.file_report(volunteer, help_request, Report.Reason.SPAM)
        client.force_login(moderator)

        assert client.get(f"/moderation/?tab={tab}").status_code == 200

    def test_decide_verification_view(self, client, moderator, volunteer):
        pending = application(volunteer)
        client.force_login(moderator)

        client.post(f"/moderation/verification/{pending.pk}/decide/", {"decision": "approve"})

        pending.refresh_from_db()
        assert pending.status == VerificationRequest.Status.APPROVED

    def test_apply_page_and_submit(self, client_logged_in_volunteer, volunteer):
        assert client_logged_in_volunteer.get("/moderation/verification/apply/").status_code == 200
        client_logged_in_volunteer.post(
            "/moderation/verification/apply/", {"city": "Львів", "about": "Студентка, маю авто"}
        )
        assert volunteer.verification_requests.filter(status="pending").exists()

    def test_report_view(self, client_logged_in_volunteer, help_request):
        page = client_logged_in_volunteer.post(
            f"/moderation/report/request/{help_request.pk}/",
            {"reason": "fraud", "comment": "Просять передоплату", "next": "/requests/"},
        )
        assert page["Location"] == "/requests/"
        assert Report.objects.count() == 1

    def test_codes_page(self, client, moderator):
        client.force_login(moderator)
        client.post("/moderation/codes/", {"organization": "Червоний Хрест", "max_uses": 5})
        assert InviteCode.objects.filter(organization="Червоний Хрест").exists()

    def test_publish_draft_view(self, client, category):
        recipient = RecipientFactory(email_verified_at=None)
        draft = request_services.create_request(new_request(), recipient)
        recipient.email_verified_at = timezone.now()
        recipient.save()
        client.force_login(recipient)

        client.post(f"/requests/{draft.pk}/publish/")

        draft.refresh_from_db()
        assert draft.status == Status.PENDING_MODERATION
