"""
Findings of the visual QA review: personal home, volunteer ratings for the
recipient's choice, status labels, lifecycle notes, name forms in
notifications, form defaults and role-aware email settings.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from django.utils.formats import date_format

from apps.accounts.forms import RecipientProfileForm
from apps.accounts.permissions import MODERATORS_GROUP
from apps.accounts.views import action_items
from apps.conversations import services as conversation_services
from apps.notifications.forms import EmailPreferencesForm
from apps.notifications.models import EmailPreferences, Notification
from apps.notifications.services import preferences_for
from apps.requests import services
from apps.requests.forms import HelpRequestForm
from apps.requests.models import HelpRequest, Response
from apps.requests.views import lifecycle_steps
from apps.reviews import services as review_services
from conftest import (
    HelpRequestFactory,
    RecipientFactory,
    ResponseFactory,
    ReviewFactory,
    VolunteerFactory,
)

pytestmark = pytest.mark.django_db
Status = HelpRequest.Status


def titles(user):
    return [item["title"] for item in action_items(user)]


def completed_pair():
    """A completed request with one accepted volunteer; nobody has rated yet."""
    recipient, volunteer = RecipientFactory(), VolunteerFactory()
    help_request = HelpRequestFactory(
        recipient=recipient, status=Status.COMPLETED, completed_at=timezone.now()
    )
    ResponseFactory(help_request=help_request, volunteer=volunteer, status=Response.Status.ACCEPTED)
    return help_request, recipient, volunteer


# ---------------------------------------------------------------------------
# Personal home
# ---------------------------------------------------------------------------


class TestActionItems:
    def test_nothing_to_do(self):
        assert action_items(RecipientFactory()) == []

    def test_item_shape(self):
        recipient = RecipientFactory()
        HelpRequestFactory(recipient=recipient, status=Status.AWAITING_CONFIRMATION)
        [item] = action_items(recipient)
        assert set(item) == {"icon", "title", "text", "url", "tone"}
        assert item["icon"].startswith("bi-")
        assert item["tone"] in ("", "warning", "success")

    def test_recipient_confirmation_links_to_the_request(self):
        recipient = RecipientFactory()
        hr = HelpRequestFactory(recipient=recipient, status=Status.AWAITING_CONFIRMATION)
        [item] = action_items(recipient)
        assert item["title"] == "Підтвердіть виконання"
        assert item["url"] == f"/requests/{hr.pk}/"
        assert item["tone"] == "warning"

    def test_recipient_pending_responses_are_counted(self):
        recipient = RecipientFactory()
        hr = HelpRequestFactory(recipient=recipient)
        ResponseFactory.create_batch(2, help_request=hr)
        ResponseFactory(help_request=hr, status=Response.Status.REJECTED)
        assert titles(recipient) == ["Нові відгуки волонтерів: 2"]

    def test_recipient_draft_and_unconfirmed_email(self):
        recipient = RecipientFactory(email_verified_at=None)
        HelpRequestFactory(recipient=recipient, status=Status.DRAFT)
        assert titles(recipient) == ["Підтвердіть email", "Опублікуйте чернетку"]

    def test_pending_review(self):
        help_request, recipient, volunteer = completed_pair()
        [item] = action_items(recipient)
        assert item["title"] == "Залиште оцінку"
        assert item["url"] == f"/reviews/create/{help_request.pk}/{volunteer.pk}/"
        assert item["tone"] == "success"

    def test_at_most_four(self):
        recipient = RecipientFactory(email_verified_at=None)
        for status in (Status.AWAITING_CONFIRMATION, Status.REJECTED, Status.DRAFT):
            HelpRequestFactory(recipient=recipient, status=status)
        ResponseFactory(help_request=HelpRequestFactory(recipient=recipient))
        assert len(action_items(recipient)) == 4

    def test_volunteer_marks_done_after_help(self):
        volunteer = VolunteerFactory(is_verified=True)
        hr = HelpRequestFactory(
            status=Status.IN_PROGRESS, needed_date=timezone.now() - timedelta(hours=1)
        )
        ResponseFactory(help_request=hr, volunteer=volunteer, status=Response.Status.ACCEPTED)
        [item] = action_items(volunteer)
        assert item["title"] == "Позначте виконання після допомоги"
        assert item["url"] == f"/requests/{hr.pk}/"
        assert item["tone"] == "warning"

    def test_volunteer_already_done_is_not_asked_again(self):
        volunteer = VolunteerFactory(is_verified=True)
        hr = HelpRequestFactory(status=Status.IN_PROGRESS)
        ResponseFactory(
            help_request=hr,
            volunteer=volunteer,
            status=Response.Status.ACCEPTED,
            done_at=timezone.now(),
        )
        assert action_items(volunteer) == []

    def test_volunteer_unread_conversation(self):
        volunteer = VolunteerFactory(is_verified=True)
        response = ResponseFactory(volunteer=volunteer, status=Response.Status.ACCEPTED)
        response.help_request.status = Status.IN_PROGRESS
        response.help_request.save()
        conversation = conversation_services.open_for(response)
        conversation_services.send(conversation, response.help_request.recipient, "Привіт")
        assert "Нові повідомлення: 1" in titles(volunteer)

    def test_unverified_volunteer_is_invited_to_apply(self):
        [item] = action_items(VolunteerFactory())
        assert item["url"] == "/moderation/verification/apply/"

    def test_moderator_sees_queue_counts(self):
        moderator = VolunteerFactory(is_verified=True)
        moderator.groups.add(Group.objects.get(name=MODERATORS_GROUP))
        HelpRequestFactory(status=Status.PENDING_MODERATION)
        [item] = action_items(moderator)
        assert item["title"] == "Запити на модерації: 1"
        assert item["url"] == "/moderation/?tab=requests"


class TestHomeView:
    def test_recipient_does_not_see_own_requests(self, client):
        recipient = RecipientFactory()
        own = HelpRequestFactory(recipient=recipient)
        other = HelpRequestFactory()
        client.force_login(recipient)
        context = client.get("/").context
        assert list(context["recent_requests"]) == [other]
        assert own not in context["recent_requests"]
        assert context["action_items"] == []

    def test_guest_gets_empty_action_items(self, client):
        HelpRequestFactory()
        context = client.get("/").context
        assert context["action_items"] == []
        assert len(context["recent_requests"]) == 1


# ---------------------------------------------------------------------------
# Request page
# ---------------------------------------------------------------------------


class TestVolunteerRatingOnResponses:
    def test_owner_sees_each_volunteer_rating(self, client):
        recipient, volunteer = RecipientFactory(), VolunteerFactory()
        ReviewFactory(target=volunteer, rating=4)
        ReviewFactory(target=volunteer, rating=5)
        hr = HelpRequestFactory(recipient=recipient)
        ResponseFactory(help_request=hr, volunteer=volunteer)
        client.force_login(recipient)

        [response] = client.get(f"/requests/{hr.pk}/").context["responses"]
        assert response.volunteer_rating.average == 4.5
        assert response.volunteer_rating.count == 2


class TestLifecycle:
    def test_recruiting_label_until_done(self):
        hr = HelpRequestFactory()
        assert lifecycle_steps(hr, 0)[1]["label"] == "Набір волонтерів"
        hr.status = Status.IN_PROGRESS
        assert lifecycle_steps(hr, 1)[1]["label"] == "Волонтерів набрано"

    def test_completed_note(self):
        hr = HelpRequestFactory(status=Status.COMPLETED, completed_at=timezone.now())
        assert lifecycle_steps(hr, 1, review_pending=True)[3]["note"] == "залиште оцінку"
        date = date_format(timezone.localtime(hr.completed_at), "j E")
        assert lifecycle_steps(hr, 1)[3]["note"] == date

    def test_detail_page_asks_for_review_only_while_pending(self, client):
        help_request, recipient, volunteer = completed_pair()
        client.force_login(recipient)
        url = f"/requests/{help_request.pk}/"
        assert client.get(url).context["lifecycle"][3]["note"] == "залиште оцінку"

        review_services.submit_review(recipient, help_request, volunteer, 5)
        assert client.get(url).context["lifecycle"][3]["note"] != "залиште оцінку"


def test_status_labels():
    assert Status.ACTIVE.label == "Шукає волонтерів"
    assert Status.IN_PROGRESS.label == "У процесі"
    assert Status.AWAITING_CONFIRMATION.label == "Чекає підтвердження"


# ---------------------------------------------------------------------------
# Names in notifications
# ---------------------------------------------------------------------------


class TestShortNames:
    def test_short_name(self):
        assert VolunteerFactory(first_name="Анна", last_name="Коваль").short_name == "Анна К."
        assert VolunteerFactory(first_name="Анна", last_name="").short_name == "Анна"

    def test_notifications_never_use_the_full_name(self):
        recipient = RecipientFactory()
        volunteer = VolunteerFactory(first_name="Анна", last_name="Коваль")
        hr = HelpRequestFactory(recipient=recipient)
        services.respond(hr, volunteer)
        response = Response.objects.get(help_request=hr)
        services.accept(response, recipient)
        conversation = conversation_services.open_for(response)
        conversation_services.send(conversation, volunteer, "Буду о 10:00")
        services.mark_done(response, volunteer)

        texts = [f"{n.title} {n.message}" for n in Notification.objects.filter(user=recipient)]
        assert "Новий відгук волонтера: Анна К." in texts[-1]
        assert all("Коваль" not in text and "від Анна" not in text for text in texts)

    def test_review_notifications(self):
        help_request, recipient, volunteer = completed_pair()
        recipient.first_name, recipient.last_name = "Ольга", "Петренко"
        recipient.save()
        review_services.submit_review(recipient, help_request, volunteer, 5)
        review_services.submit_review(volunteer, help_request, recipient, 4)

        texts = [n.message for n in Notification.objects.filter(user=volunteer)]
        assert any("Ольга П." in text for text in texts)
        assert all("Петренко" not in text and "від " not in text for text in texts)

    def test_conversation_system_message(self):
        response = ResponseFactory(status=Response.Status.ACCEPTED)
        conversation = conversation_services.open_for(response)
        assert "поділитися своїм можна кнопкою під розмовою" in conversation.messages.get().body


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


class TestForms:
    def test_create_form_has_no_preselected_format(self):
        form = HelpRequestForm()
        assert form["help_format"].value() is None
        assert "checked" not in str(form["help_format"])
        assert form.fields["category"].empty_label == "Оберіть категорію"

    def test_format_is_required(self):
        form = HelpRequestForm(data={"title": "x"})
        assert form.errors["help_format"] == ["Оберіть формат допомоги."]

    def test_edit_form_keeps_the_saved_format(self):
        hr = HelpRequestFactory(help_format=HelpRequest.HelpFormat.REMOTE)
        assert HelpRequestForm(instance=hr)["help_format"].value() == "remote"

    def test_situation_type_blank_choice(self):
        choices = list(RecipientProfileForm().fields["situation_type"].choices)
        assert choices[0] == ("", "Не вказувати")
        assert all("---" not in str(label) for _, label in choices)


class TestEmailPreferencesForm:
    def test_recipient_has_no_nearby_switch(self):
        form = EmailPreferencesForm(user=RecipientFactory())
        assert "nearby" not in form.fields
        assert form.fields["responses"].help_text == "Коли волонтер відгукується на ваш запит"

    def test_volunteer_texts(self):
        form = EmailPreferencesForm(user=VolunteerFactory())
        assert "nearby" in form.fields
        assert form.fields["responses"].help_text == (
            "Коли вас прийняли або обрали іншого волонтера"
        )
        assert all(field.help_text for field in form.fields.values())

    def test_saving_as_recipient_keeps_the_hidden_value(self, client):
        recipient = RecipientFactory()
        preferences = preferences_for(recipient)
        preferences.nearby = True
        preferences.save()
        client.force_login(recipient)

        page = client.get("/notifications/email-settings/")
        assert "nearby" not in page.context["form"].fields
        client.post("/notifications/email-settings/", {"responses": "on"})

        preferences = EmailPreferences.objects.get(user=recipient)
        assert preferences.nearby and preferences.responses
        assert not preferences.messages


# ---------------------------------------------------------------------------
# Dashboard tab counters
# ---------------------------------------------------------------------------


class TestSectionCounts:
    def test_requests(self):
        from apps.requests.views import _section_counts, request_section

        items = [
            HelpRequest(status=Status.AWAITING_CONFIRMATION),
            HelpRequest(status=Status.DRAFT),
            HelpRequest(status=Status.ACTIVE),
            HelpRequest(status=Status.IN_PROGRESS),
            HelpRequest(status=Status.EXPIRED),
        ]
        items[2].pending_count = 0
        assert _section_counts(items, request_section) == {"needs": 2, "current": 2, "past": 1}
        items[2].pending_count = 3
        assert request_section(items[2]) == "needs"

    def test_responses(self):
        from apps.requests.views import _section_counts, response_section

        def resp(status, request_status, done=False):
            return Response(
                status=status,
                help_request=HelpRequest(status=request_status),
                done_at=timezone.now() if done else None,
            )

        R = Response.Status
        items = [
            resp(R.ACCEPTED, Status.IN_PROGRESS),
            resp(R.ACCEPTED, Status.IN_PROGRESS, done=True),
            resp(R.ACCEPTED, Status.AWAITING_CONFIRMATION),
            resp(R.PENDING, Status.ACTIVE),
            resp(R.ACCEPTED, Status.COMPLETED),
            resp(R.REJECTED, Status.IN_PROGRESS),
        ]
        assert _section_counts(items, response_section) == {"needs": 1, "current": 3, "past": 2}
