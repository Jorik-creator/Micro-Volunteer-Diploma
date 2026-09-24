"""
Single entry point for creating notifications.

Business code calls notify() explicitly at the moment something happens,
instead of relying on model signals (see docs/adr/0003).
"""

from apps.requests.utils import haversine_distance

from .models import Notification


def notify(user, type, title, message, help_request=None):
    """Create an in-app notification for one user."""
    return Notification.objects.create(
        user=user,
        type=type,
        title=title,
        message=message,
        related_request=help_request,
    )


def notify_many(users, type, title, message, help_request=None):
    """Create the same notification for several users in one query."""
    Notification.objects.bulk_create(
        Notification(
            user=user,
            type=type,
            title=title,
            message=message,
            related_request=help_request,
        )
        for user in users
    )


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
