"""
Single entry point for creating notifications.

Business code calls notify() explicitly at the moment something happens,
instead of relying on model signals (see docs/adr/0003).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from apps.requests.utils import haversine_distance

from .models import EMAIL_GROUPS, EmailPreferences, Notification

logger = logging.getLogger(__name__)


def notify(user, type, title, message, help_request=None, link=None):
    """Create an in-app notification and, if the user wants it, an email."""
    notification = Notification.objects.create(
        user=user,
        type=type,
        title=title,
        message=message,
        related_request=help_request,
        link=link or "",
    )
    _queue_email(user, notification)
    return notification


def notify_many(users, type, title, message, help_request=None, link=None):
    """Create the same notification for several users in one query."""
    created = Notification.objects.bulk_create(
        Notification(
            user=user,
            type=type,
            title=title,
            message=message,
            related_request=help_request,
            link=link or "",
        )
        for user in users
    )
    for notification in created:
        _queue_email(notification.user, notification)


def preferences_for(user):
    preferences, _ = EmailPreferences.objects.get_or_create(user=user)
    return preferences


def _wants_email(user, notification):
    if user.is_demo or not user.is_active or not user.email or not user.email_verified_at:
        return False
    group = EMAIL_GROUPS.get(notification.type)
    return bool(group) and preferences_for(user).wants(group)


def _queue_email(user, notification):
    """Send after commit so a rolled-back action never emails anybody."""
    if _wants_email(user, notification):
        transaction.on_commit(lambda: _send_email(user, notification))


def _send_email(user, notification):
    site = settings.SITE_URL.rstrip("/")
    context = {
        "user": user,
        "notification": notification,
        "link": site + notification.url,
        "settings_link": site + reverse("notifications:email-settings"),
    }
    try:
        send_mail(
            subject=f"{notification.title} — MicroVolunteer",
            message=render_to_string("emails/notification.txt", context),
            from_email=None,
            recipient_list=[user.email],
            html_message=render_to_string("emails/notification.html", context),
        )
    except Exception:  # email provider down must never break the action itself
        logger.exception("Could not email notification %s", notification.pk)


def _volunteer_is_nearby(volunteer, help_request):
    """
    Radius check when both sides have coordinates; otherwise fall back to a
    shared word of the address (city/district) — conservative on purpose.
    """
    radius_km = volunteer.volunteer_profile.radius_km
    has_coords = None not in (
        volunteer.latitude,
        volunteer.longitude,
        help_request.latitude,
        help_request.longitude,
    )
    if has_coords:
        distance = haversine_distance(
            volunteer.latitude,
            volunteer.longitude,
            help_request.latitude,
            help_request.longitude,
        )
        return distance <= radius_km

    volunteer_address = (volunteer.address or "").casefold()
    request_address = (help_request.address or "").casefold()
    return bool(request_address) and any(
        len(part) >= 3 and part in request_address
        for part in volunteer_address.replace(",", " ").split()
    )


def notify_nearby_volunteers(help_request):
    """
    Tell available verified volunteers about a newly published request when
    it matches their categories (or they chose none) and location.
    Returns the number of notified volunteers.
    """
    from django.db.models import Q

    from apps.accounts.models import User

    candidates = (
        User.objects.filter(
            user_type=User.UserType.VOLUNTEER,
            is_active=True,
            is_verified=True,
            volunteer_profile__is_available=True,
        )
        .exclude(pk=help_request.recipient_id)
        .select_related("volunteer_profile")
    )
    if help_request.category_id:
        candidates = candidates.filter(
            Q(volunteer_profile__categories__isnull=True)
            | Q(volunteer_profile__categories=help_request.category_id)
        ).distinct()

    already_notified = set(
        Notification.objects.filter(
            related_request=help_request, type=Notification.Type.NEW_NEARBY_REQUEST
        ).values_list("user_id", flat=True)
    )
    recipients = [
        volunteer
        for volunteer in candidates
        if volunteer.pk not in already_notified and _volunteer_is_nearby(volunteer, help_request)
    ]
    notify_many(
        recipients,
        Notification.Type.NEW_NEARBY_REQUEST,
        "Новий запит поблизу",
        f"Поруч з вами з'явився запит: «{help_request.title}».",
        help_request,
    )
    return len(recipients)
