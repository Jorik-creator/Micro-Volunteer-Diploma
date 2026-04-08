"""
Tests for the notifications app.

Covers: Notification model, defaults, string representation.
"""

import pytest
from unittest.mock import patch
from django.utils import timezone

from apps.notifications.models import Notification

from conftest import NotificationFactory, RecipientFactory


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
        n1 = NotificationFactory(user=user, title="First")
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
