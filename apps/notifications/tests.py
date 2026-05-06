"""
Tests for the notifications app.

Covers: Notification model, defaults, string representation.
"""

import pytest
from unittest.mock import patch
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.signals import on_new_request_created
from apps.requests.models import HelpRequest

from conftest import (
    CategoryFactory,
    HelpRequestFactory,
    NotificationFactory,
    RecipientFactory,
    VolunteerFactory,
)


# ===================================================================
# NOTIFICATION MODEL TESTS
# ===================================================================


class TestNotificationModel:
    """Tests for the Notification model."""

    def test_notification_str_unread(self, notification):
        """Unread notification __str__ starts with ● symbol."""
        result = str(notification)
        assert "●" in result

    def test_notification_str_read(self, db):
        """Read notification __str__ starts with ✓ symbol."""
        notif = NotificationFactory(is_read=True)
        result = str(notif)
        assert "✓" in result

    def test_notification_default_unread(self, notification):
        """New notifications default to is_read=False."""
        assert notification.is_read is False

    def test_notification_ordering(self, db):
        """Notifications are ordered by -created_at (newest first)."""
        user = RecipientFactory()
        NotificationFactory(user=user, title="First")
        n2 = NotificationFactory(user=user, title="Second")
        notifications = list(
            Notification.objects.filter(user=user, title__in=["First", "Second"])
        )
        assert notifications[0] == n2  # Second created → first in queryset

    def test_ordering_when_same_timestamp(self, db):
        """When created_at is identical, higher id (newer row) comes first."""
        fixed_time = timezone.now()
        user = RecipientFactory()
        with patch("django.utils.timezone.now", return_value=fixed_time):
            n1 = NotificationFactory(user=user, title="First")
            n2 = NotificationFactory(user=user, title="Second")
        # Both have same created_at — tie broken by -id: n2.id > n1.id
        assert n2.id > n1.id
        notifications = list(Notification.objects.filter(user=user))
        assert notifications[0] == n2
        assert notifications[1] == n1

    def test_notification_types(self, db):
        """All notification types are valid choices."""
        valid_types = [choice[0] for choice in Notification.Type.choices]
        assert "new_response" in valid_types
        assert "request_accepted" in valid_types
        assert "request_completed" in valid_types
        assert "new_review" in valid_types
        assert "new_nearby_request" in valid_types


# ===================================================================
# NOTIFICATION VIEWS TESTS
# ===================================================================


class TestNotificationViews:
    """Tests for NotificationListView, mark_read, and mark_all_read views."""

    @pytest.mark.django_db
    def test_notification_list_shows_own_only(
        self, client_logged_in_volunteer, volunteer
    ):
        """Notification list returns only the current user's notifications."""
        # Arrange — 2 notifications for the logged-in volunteer, 1 for another user
        n1 = NotificationFactory(user=volunteer)
        n2 = NotificationFactory(user=volunteer)
        other_user = RecipientFactory()
        NotificationFactory(user=other_user)

        # Act
        response = client_logged_in_volunteer.get("/notifications/")

        # Assert — 200 OK and only the 2 own notifications in context
        assert response.status_code == 200
        context_notifications = list(response.context["notifications"])
        assert len(context_notifications) == 2
        assert n1 in context_notifications
        assert n2 in context_notifications

    @pytest.mark.django_db
    def test_mark_read(self, client_logged_in_volunteer, volunteer):
        """POST to mark-read sets is_read=True and redirects to notifications list."""
        # Arrange — unread notification belonging to the logged-in volunteer
        notif = NotificationFactory(user=volunteer, is_read=False)

        # Act
        response = client_logged_in_volunteer.post(
            f"/notifications/mark-read/{notif.pk}/"
        )

        # Assert — notification is now read and response is a redirect
        notif.refresh_from_db()
        assert notif.is_read is True
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_mark_read_other_user(self, client_logged_in_volunteer):
        """POST to mark-read for another user's notification returns 404."""
        # Arrange — notification belonging to a different user
        other_user = RecipientFactory()
        notif = NotificationFactory(user=other_user, is_read=False)

        # Act
        response = client_logged_in_volunteer.post(
            f"/notifications/mark-read/{notif.pk}/"
        )

        # Assert — 404 because the notification does not belong to the requester
        assert response.status_code == 404

    @pytest.mark.django_db
    def test_mark_all_read(self, client_logged_in_volunteer, volunteer):
        """POST to mark-all-read sets is_read=True on all own unread notifications."""
        # Arrange — 3 unread notifications for the volunteer, 1 for another user
        n1 = NotificationFactory(user=volunteer, is_read=False)
        n2 = NotificationFactory(user=volunteer, is_read=False)
        n3 = NotificationFactory(user=volunteer, is_read=False)
        other_user = RecipientFactory()
        other_notif = NotificationFactory(user=other_user, is_read=False)

        # Act
        response = client_logged_in_volunteer.post("/notifications/mark-all-read/")

        # Assert — all 3 own notifications are now read
        n1.refresh_from_db()
        n2.refresh_from_db()
        n3.refresh_from_db()
        assert n1.is_read is True
        assert n2.is_read is True
        assert n3.is_read is True

        # Other user's notification must remain unchanged
        other_notif.refresh_from_db()
        assert other_notif.is_read is False

        assert response.status_code == 302

    @pytest.mark.django_db
    def test_notification_count_returns_own_unread_count(
        self, client_logged_in_volunteer, volunteer
    ):
        """GET notification count returns only the current user's unread total."""
        # Arrange — 2 own unread, 1 own read, 1 unread for another user
        NotificationFactory(user=volunteer, is_read=False)
        NotificationFactory(user=volunteer, is_read=False)
        NotificationFactory(user=volunteer, is_read=True)
        NotificationFactory(user=RecipientFactory(), is_read=False)

        # Act
        response = client_logged_in_volunteer.get("/notifications/count/")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"count": 2}

    @pytest.mark.django_db
    def test_notification_count_allows_get_only(self, client_logged_in_volunteer):
        """Notification count is a read-only polling endpoint: POST returns 405."""
        response = client_logged_in_volunteer.post("/notifications/count/")
        assert response.status_code == 405

    @pytest.mark.django_db
    def test_unauthenticated_redirect(self):
        """Unauthenticated GET to /notifications/ redirects to login."""
        from django.test import Client

        # Arrange — anonymous client (no session)
        anon_client = Client()

        # Act
        response = anon_client.get("/notifications/")

        # Assert — 302 redirect pointing to the login page
        assert response.status_code == 302
        assert "login" in response.url or "accounts" in response.url


# ===================================================================
# NOTIFICATION SIGNAL TESTS
# ===================================================================


class TestNotificationSignals:
    """Tests for notification-producing signals."""

    @pytest.mark.django_db
    def test_new_request_notifies_matching_verified_volunteer(self):
        """A verified available volunteer in radius receives NEW_NEARBY_REQUEST."""
        # Arrange
        category = CategoryFactory()
        volunteer = VolunteerFactory(
            is_verified=True,
            address="Київ",
            latitude=50.4501,
            longitude=30.5234,
        )
        volunteer.volunteer_profile.categories.add(category)
        volunteer.volunteer_profile.radius_km = 10
        volunteer.volunteer_profile.save()

        # Act — HelpRequestFactory save triggers post_save.
        help_request = HelpRequestFactory(
            category=category,
            address="Київ, Хрещатик",
            latitude=50.4505,
            longitude=30.5238,
        )

        # Assert
        assert Notification.objects.filter(
            user=volunteer,
            type=Notification.Type.NEW_NEARBY_REQUEST,
            related_request=help_request,
        ).exists()

    @pytest.mark.django_db
    def test_new_request_skips_unverified_volunteer(self):
        """Unverified volunteers do not receive nearby request notifications."""
        # Arrange
        volunteer = VolunteerFactory(
            is_verified=False,
            address="Київ",
            latitude=50.4501,
            longitude=30.5234,
        )

        # Act
        help_request = HelpRequestFactory(
            address="Київ, Хрещатик",
            latitude=50.4505,
            longitude=30.5238,
        )

        # Assert
        assert not Notification.objects.filter(
            user=volunteer,
            type=Notification.Type.NEW_NEARBY_REQUEST,
            related_request=help_request,
        ).exists()

    @pytest.mark.django_db
    def test_new_request_notification_is_idempotent(self):
        """Calling the signal twice still leaves one nearby notification."""
        # Arrange
        volunteer = VolunteerFactory(
            is_verified=True,
            address="Київ",
            latitude=50.4501,
            longitude=30.5234,
        )
        help_request = HelpRequestFactory(
            address="Київ, Хрещатик",
            latitude=50.4505,
            longitude=30.5238,
        )

        # Act — simulate a duplicate delivery of the same post_save event.
        on_new_request_created(
            sender=HelpRequest,
            instance=help_request,
            created=True,
        )

        # Assert
        assert Notification.objects.filter(
            user=volunteer,
            type=Notification.Type.NEW_NEARBY_REQUEST,
            related_request=help_request,
        ).count() == 1
