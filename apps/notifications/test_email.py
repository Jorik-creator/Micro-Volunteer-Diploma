"""
Email delivery of notifications, preferences and password reset.
"""

import pytest
from django.core import mail

from apps.notifications.models import EmailPreferences, Notification
from apps.notifications.services import notify, preferences_for
from conftest import RecipientFactory, VolunteerFactory

pytestmark = pytest.mark.django_db


def send(user, type=Notification.Type.REQUEST_ACCEPTED):
    notify(user, type, "Вас прийнято", "Запит «Ліки»")


class TestNotificationEmails:
    def test_sent_after_commit(self, django_capture_on_commit_callbacks):
        user = VolunteerFactory()
        with django_capture_on_commit_callbacks(execute=True):
            send(user)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]
        assert "/notifications/email-settings/" in mail.outbox[0].body

    def test_respects_preferences(self, django_capture_on_commit_callbacks):
        user = VolunteerFactory()
        preferences = preferences_for(user)
        preferences.responses = False
        preferences.save()

        with django_capture_on_commit_callbacks(execute=True):
            send(user)

        assert mail.outbox == []
        assert Notification.objects.filter(user=user).exists()  # still on the site

    def test_nearby_is_opt_in(self, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            send(VolunteerFactory(), Notification.Type.NEW_NEARBY_REQUEST)
        assert mail.outbox == []

    @pytest.mark.parametrize(
        "user_kwargs", [{"is_demo": True}, {"email_verified_at": None}, {"is_active": False}]
    )
    def test_never_emails_demo_unconfirmed_or_blocked(
        self, django_capture_on_commit_callbacks, user_kwargs
    ):
        with django_capture_on_commit_callbacks(execute=True):
            send(VolunteerFactory(**user_kwargs))
        assert mail.outbox == []

    def test_provider_failure_does_not_break_action(
        self, django_capture_on_commit_callbacks, monkeypatch
    ):
        from apps.notifications import services

        def broken(*args, **kwargs):
            raise ConnectionError("Brevo down")

        monkeypatch.setattr(services, "send_mail", broken)
        with django_capture_on_commit_callbacks(execute=True):
            send(VolunteerFactory())  # must not raise


class TestSettingsPage:
    def test_toggle(self, client):
        user = RecipientFactory()
        client.force_login(user)

        assert client.get("/notifications/email-settings/").status_code == 200
        client.post("/notifications/email-settings/", {"lifecycle": "on", "account": "on"})

        preferences = EmailPreferences.objects.get(user=user)
        assert preferences.lifecycle and preferences.account
        assert not preferences.messages


class TestPasswordReset:
    def test_sends_link(self, client):
        user = VolunteerFactory()

        client.post("/accounts/password-reset/", {"email": user.email})

        assert len(mail.outbox) == 1
        assert "/accounts/reset/" in mail.outbox[0].body

    def test_demo_account_cannot_be_reset(self, client):
        demo = VolunteerFactory(is_demo=True)
        client.post("/accounts/password-reset/", {"email": demo.email})
        assert mail.outbox == []

    def test_pages_render(self, client):
        assert client.get("/accounts/password-reset/").status_code == 200
        assert client.get("/accounts/password-reset/sent/").status_code == 200
        assert client.get("/accounts/reset/done/").status_code == 200

    def test_demo_cannot_change_password_or_email(self, client):
        demo = VolunteerFactory(is_demo=True)
        client.force_login(demo)

        assert client.get("/accounts/password-change/")["Location"] == "/accounts/profile/"
        form = client.get("/accounts/profile/edit/").context["form"]
        assert form.fields["email"].disabled


class TestEmailChange:
    def test_changing_email_requires_new_confirmation(self, client):
        user = VolunteerFactory()
        client.force_login(user)
        form = client.get("/accounts/profile/edit/").context["form"]
        data = {name: form.initial.get(name) or "" for name in form.fields}
        data["email"] = "new-address@example.com"
        data["role-radius_km"] = 10  # volunteer part of the form

        client.post("/accounts/profile/edit/", data)

        user.refresh_from_db()
        assert user.email == "new-address@example.com"
        assert user.email_verified_at is None
        assert len(mail.outbox) == 1
