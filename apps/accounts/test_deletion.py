"""Self-service account deletion and legal pages."""

import pytest
from django.utils import timezone

from apps.accounts.deletion import REMOVED_TEXT, DeletionError, delete_account
from apps.conversations import services as conversation_services
from apps.conversations.models import Conversation
from apps.moderation import services as moderation
from apps.notifications.models import Notification
from apps.requests import services as request_services
from apps.requests.models import HelpRequest, Response
from apps.reviews.models import Review
from conftest import HelpRequestFactory, ResponseFactory, ReviewFactory, VolunteerFactory

pytestmark = pytest.mark.django_db


class TestDeleteAccount:
    def test_erases_personal_data_and_blocks_login(self, recipient):
        recipient.phone = "+380501112233"
        recipient.address = "Київ, Хрещатик 1"
        recipient.save()

        delete_account(recipient)

        recipient.refresh_from_db()
        assert recipient.first_name == "Видалений"
        assert recipient.email.endswith("@deleted.invalid")
        assert recipient.phone == "" and recipient.address == ""
        assert not recipient.is_active
        assert not recipient.has_usable_password()

    def test_open_requests_cancelled_and_volunteers_told(self, recipient, volunteer):
        help_request = HelpRequestFactory(
            recipient=recipient,
            on_behalf=True,
            beneficiary_name="Ганна",
            beneficiary_phone="+380671",
        )
        ResponseFactory(help_request=help_request, volunteer=volunteer)

        delete_account(recipient)

        help_request.refresh_from_db()
        assert help_request.status == HelpRequest.Status.CANCELLED
        assert help_request.beneficiary_phone == "" and help_request.address == ""
        assert help_request.description == REMOVED_TEXT
        assert Notification.objects.filter(user=volunteer, type="request_cancelled").exists()

    def test_volunteer_leaves_accepted_requests(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        response = ResponseFactory(help_request=help_request, volunteer=volunteer)
        request_services.accept(response, recipient)

        delete_account(volunteer)

        response.refresh_from_db()
        help_request.refresh_from_db()
        assert response.status == Response.Status.WITHDRAWN
        assert help_request.status == HelpRequest.Status.ACTIVE

    def test_messages_erased_reviews_kept(self, recipient, volunteer):
        help_request = HelpRequestFactory(recipient=recipient)
        response = ResponseFactory(help_request=help_request, volunteer=volunteer)
        request_services.accept(response, recipient)
        chat = Conversation.objects.get(help_request=help_request)
        conversation_services.send(chat, volunteer, "Мій номер 0501234567")
        review = ReviewFactory(author=volunteer, target=recipient, published_at=timezone.now())
        moderation.apply(volunteer, city="Київ", about="Про себе")

        delete_account(volunteer)

        assert chat.messages.get(sender=volunteer).body == REMOVED_TEXT
        assert Review.objects.filter(pk=review.pk).exists()
        assert not volunteer.verification_requests.exists()

    def test_demo_account_cannot_be_deleted(self):
        with pytest.raises(DeletionError):
            delete_account(VolunteerFactory(is_demo=True))

    def test_view_requires_password(self, client, volunteer):
        client.force_login(volunteer)

        client.post("/accounts/delete/", {"password": "wrong", "confirm": "on"})
        volunteer.refresh_from_db()
        assert volunteer.is_active

        page = client.post("/accounts/delete/", {"password": "TestPass123!", "confirm": "on"})
        volunteer.refresh_from_db()
        assert page["Location"] == "/"
        assert not volunteer.is_active
        assert "_auth_user_id" not in client.session


class TestLegal:
    def test_pages_render(self, client):
        assert "Політика конфіденційності" in client.get("/privacy/").content.decode()
        assert "Правила платформи" in client.get("/rules/").content.decode()

    def test_registration_requires_consent(self, client):
        page = client.post(
            "/accounts/register/",
            {
                "username": "nope",
                "email": "nope@example.com",
                "first_name": "Н",
                "last_name": "Н",
                "user_type": "volunteer",
                "password1": "Str0ng-pass-123",
                "password2": "Str0ng-pass-123",
            },
        )
        assert page.status_code == 200
        assert "Без згоди" in page.content.decode()
