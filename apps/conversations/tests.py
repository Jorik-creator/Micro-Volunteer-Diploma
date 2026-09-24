"""
Tests for recipient ↔ volunteer conversations (docs/adr/0007).
"""

import pytest
from django.contrib.auth.models import Group

from apps.accounts.permissions import MODERATORS_GROUP
from apps.conversations import services
from apps.conversations.models import Conversation, Message
from apps.conversations.services import ConversationError
from apps.moderation import services as moderation
from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.requests import services as request_services
from apps.requests.models import HelpRequest, Response
from conftest import ResponseFactory, VolunteerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat(help_request, volunteer):
    """Conversation opened by accepting the volunteer."""
    response = ResponseFactory(help_request=help_request, volunteer=volunteer)
    request_services.accept(response, help_request.recipient)
    return Conversation.objects.get(help_request=help_request, volunteer=volunteer)


class TestLifecycle:
    def test_accept_opens_conversation_with_system_note(self, chat):
        assert chat.is_writable
        assert chat.messages.get().kind == Message.Kind.SYSTEM

    def test_withdrawal_makes_it_read_only(self, chat, volunteer):
        response = Response.objects.get(help_request=chat.help_request, volunteer=volunteer)
        request_services.withdraw(response, volunteer, "Захворів")

        assert not chat.is_writable
        with pytest.raises(ConversationError):
            services.send(chat, volunteer, "Привіт")

    def test_completion_closes_it(self, chat, recipient):
        request_services.confirm_completion(chat.help_request, recipient)
        chat.help_request.refresh_from_db()
        assert not chat.is_writable


class TestSending:
    def test_send_and_notify_other_side_once(self, chat, volunteer, recipient):
        services.send(chat, volunteer, "Буду о 15:00")
        chat.refresh_from_db()
        services.send(chat, volunteer, "Вже виїжджаю")

        notes = Notification.objects.filter(user=recipient, type=Notification.Type.NEW_MESSAGE)
        assert notes.count() == 1  # throttled to one per 10 minutes

    def test_outsider_cannot_write(self, chat):
        with pytest.raises(ConversationError):
            services.send(chat, VolunteerFactory(), "Спам")

    def test_empty_and_long_rejected(self, chat, volunteer):
        with pytest.raises(ConversationError):
            services.send(chat, volunteer, "   ")
        with pytest.raises(ConversationError):
            services.send(chat, volunteer, "x" * 1001)

    def test_rate_limit(self, chat, volunteer, monkeypatch):
        monkeypatch.setattr(services, "RATE_LIMIT", 2)
        services.send(chat, volunteer, "1")
        services.send(chat, volunteer, "2")
        with pytest.raises(ConversationError):
            services.send(chat, volunteer, "3")

    def test_phone_shared_only_on_request(self, chat, volunteer):
        volunteer.phone = "+380501234567"
        volunteer.save()

        message = services.share_phone(chat, volunteer)

        assert message.kind == Message.Kind.PHONE
        with pytest.raises(ConversationError):
            services.share_phone(chat, volunteer)

    def test_phone_needed_in_profile(self, chat, volunteer):
        volunteer.phone = ""
        with pytest.raises(ConversationError):
            services.share_phone(chat, volunteer)

    def test_unread_count(self, chat, volunteer, recipient):
        chat.mark_read(recipient)
        chat.mark_read(volunteer)
        services.send(chat, volunteer, "Привіт")

        assert services.unread_count(recipient) == 1
        assert services.unread_count(volunteer) == 0


class TestViews:
    def test_page_renders_text_without_links(self, client, chat, volunteer, recipient):
        services.send(chat, volunteer, "Дивіться https://evil.example/login <b>тут</b>")
        client.force_login(recipient)

        body = client.get(f"/conversations/{chat.pk}/").content.decode()

        assert "https://evil.example/login" in body
        assert 'href="https://evil.example' not in body  # never clickable
        assert "&lt;b&gt;" in body  # escaped

    def test_post_sends(self, client, chat, recipient):
        client.force_login(recipient)
        client.post(f"/conversations/{chat.pk}/", {"body": "Дякую!"})
        assert chat.messages.filter(sender=recipient).exists()

    def test_polling_returns_new_messages(self, client, chat, volunteer, recipient):
        last = chat.messages.last().pk
        services.send(chat, volunteer, "Нове")
        client.force_login(recipient)

        data = client.get(f"/conversations/{chat.pk}/messages/?after={last}").json()

        assert [m["body"] for m in data["messages"]] == ["Нове"]
        assert data["writable"] is True

    def test_stranger_gets_404(self, client, chat):
        client.force_login(VolunteerFactory())
        assert client.get(f"/conversations/{chat.pk}/").status_code == 404

    def test_moderator_only_with_report(self, client, chat, volunteer, recipient):
        moderator = VolunteerFactory()
        moderator.groups.add(Group.objects.get(name=MODERATORS_GROUP))
        client.force_login(moderator)
        assert client.get(f"/conversations/{chat.pk}/").status_code == 404

        message = services.send(chat, volunteer, "Переведіть 500 грн на картку")
        moderation.file_report(recipient, message, Report.Reason.FRAUD)

        assert client.get(f"/conversations/{chat.pk}/").status_code == 200
        assert client.post(f"/conversations/{chat.pk}/", {"body": "x"}).status_code == 404

    def test_acting_on_message_report_hides_it(self, chat, volunteer, recipient):
        moderator = VolunteerFactory()
        message = services.send(chat, volunteer, "Образа")
        report = moderation.file_report(recipient, message, Report.Reason.OFFENSIVE)

        moderation.act_on_report(report, moderator)

        assert message.pk not in services.visible_messages(chat).values_list("pk", flat=True)

    def test_list_page(self, client, chat, recipient):
        client.force_login(recipient)
        assert chat.help_request.title in client.get("/conversations/").content.decode()

    def test_request_page_links_to_chat(self, client, chat, volunteer):
        client.force_login(volunteer)
        body = client.get(f"/requests/{chat.help_request.pk}/").content.decode()
        assert f"/conversations/{chat.pk}/" in body


class TestOnBehalf:
    def test_beneficiary_contact_shown_to_accepted_volunteer(self, client, recipient, volunteer):
        from conftest import HelpRequestFactory

        help_request = HelpRequestFactory(
            recipient=recipient,
            on_behalf=True,
            beneficiary_name="Ганна Петрівна",
            beneficiary_phone="+380671112233",
        )
        request_services.accept(
            ResponseFactory(help_request=help_request, volunteer=volunteer), recipient
        )
        client.force_login(volunteer)

        body = client.get(f"/requests/{help_request.pk}/").content.decode()

        assert "Ганна Петрівна" in body and "+380671112233" in body

    def test_form_requires_beneficiary_contact(self, category):
        from apps.requests.forms import HelpRequestForm

        form = HelpRequestForm(
            {
                "title": "Ліки для бабусі",
                "description": "Забрати в аптеці",
                "category": category.pk,
                "help_format": "doorstep",
                "urgency": "medium",
                "needed_date": "2099-01-01T10:00",
                "duration": "30min",
                "volunteers_needed": 1,
                "address": "Київ",
                "on_behalf": "on",
            }
        )
        assert not form.is_valid()
        assert "beneficiary_phone" in form.errors

    def test_phone_not_leaked_to_public(self, client):
        from conftest import HelpRequestFactory

        help_request = HelpRequestFactory(
            on_behalf=True, beneficiary_name="Ганна", beneficiary_phone="+380671112233"
        )
        body = client.get(f"/requests/{help_request.pk}/").content.decode()
        assert "+380671112233" not in body
        assert help_request.status == HelpRequest.Status.ACTIVE
