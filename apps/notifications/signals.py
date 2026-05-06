from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.reviews.models import Review
from apps.requests.models import HelpRequest, Response
from apps.requests.utils import haversine_distance


def _display_name(user):
    """Return a stable display name for notification copy."""
    return user.get_full_name() or user.username


def _volunteer_matches_request(volunteer, help_request):
    """
    Decide whether a volunteer should be notified about a new request.

    Matching is intentionally conservative:
    - volunteer must have an available profile (filtered before this helper),
    - if the volunteer picked categories, the request category must be among them,
    - if both sides have coordinates, the request must be inside volunteer radius,
    - otherwise fall back to requiring a shared address/city substring.
    """
    profile = getattr(volunteer, "volunteer_profile", None)
    if profile is None or not profile.is_available:
        return False

    if help_request.category_id and profile.categories.exists():
        if not profile.categories.filter(pk=help_request.category_id).exists():
            return False

    if (
        volunteer.latitude is not None
        and volunteer.longitude is not None
        and help_request.latitude is not None
        and help_request.longitude is not None
    ):
        distance_km = haversine_distance(
            volunteer.latitude,
            volunteer.longitude,
            help_request.latitude,
            help_request.longitude,
        )
        return distance_km <= profile.radius_km

    volunteer_address = (volunteer.address or "").casefold()
    request_address = (help_request.address or "").casefold()
    if not volunteer_address or not request_address:
        return False

    return any(
        len(part) >= 3 and part in request_address
        for part in volunteer_address.replace(",", " ").split()
    )


def create_response_status_notification(response):
    """Create an accepted/rejected notification for a volunteer response."""
    if response.status == Response.Status.ACCEPTED:
        Notification.objects.get_or_create(
            user=response.volunteer,
            type=Notification.Type.REQUEST_ACCEPTED,
            related_request=response.help_request,
            defaults={
                "title": "Вас підтверджено як волонтера",
                "message": f"Запит '{response.help_request.title}' тепер в роботі",
            },
        )

    elif response.status == Response.Status.REJECTED:
        Notification.objects.get_or_create(
            user=response.volunteer,
            type=Notification.Type.REQUEST_REJECTED,
            related_request=response.help_request,
            defaults={
                "title": "Ваш відгук не прийнято",
                "message": (
                    f"На жаль, ваш відгук на запит "
                    f"'{response.help_request.title}' відхилено."
                ),
            },
        )


@receiver(post_save, sender=Review)
def on_review_created(sender, instance, created, **kwargs):
    """Notify the review target when a new review is posted about them."""
    if not created:
        return

    review = instance
    # Truncate comment to 100 chars to keep the message concise
    comment_preview = review.comment[:100]

    Notification.objects.get_or_create(
        user=review.target,
        type=Notification.Type.NEW_REVIEW,
        related_request=review.help_request,
        defaults={
            "title": f"{_display_name(review.author)} залишив(ла) відгук про вас",
            "message": f"Оцінка: {review.rating}/5. {comment_preview}",
        },
    )


@receiver(post_save, sender=Response)
def on_response_status_change(sender, instance, created, update_fields, **kwargs):
    """Notify the volunteer when their response is accepted or rejected by the recipient."""
    # Only react to status updates, not new records
    if created:
        return

    # Respect selective saves: skip if update_fields doesn't include 'status'
    if update_fields is not None and "status" not in update_fields:
        return

    create_response_status_notification(instance)


@receiver(post_save, sender=Response)
def on_response_received(sender, instance, created, **kwargs):
    """Notify the recipient when a volunteer submits a new response to their request."""
    if not created:
        return

    recipient = instance.help_request.recipient

    Notification.objects.get_or_create(
        user=recipient,
        type=Notification.Type.NEW_RESPONSE,
        related_request=instance.help_request,
        defaults={
            "title": f"{_display_name(instance.volunteer)} відгукнувся(лась) на ваш запит",
            "message": (
                f"Запит: '{instance.help_request.title}'. "
                "Перегляньте відгуки та оберіть волонтера."
            ),
        },
    )


@receiver(post_save, sender=HelpRequest)
def on_new_request_created(sender, instance, created, **kwargs):
    """Notify matching verified volunteers when a new active request is created."""
    if not created:
        return

    if instance.status != HelpRequest.Status.ACTIVE:
        return

    volunteers = (
        User.objects.filter(
            user_type=User.UserType.VOLUNTEER,
            is_active=True,
            is_verified=True,
            volunteer_profile__is_available=True,
        )
        .select_related("volunteer_profile")
        .prefetch_related("volunteer_profile__categories")
    )

    for volunteer in volunteers:
        if not _volunteer_matches_request(volunteer, instance):
            continue

        Notification.objects.get_or_create(
            user=volunteer,
            type=Notification.Type.NEW_NEARBY_REQUEST,
            related_request=instance,
            defaults={
                "title": "Новий запит поблизу",
                "message": f"Поруч з вами з'явився запит: '{instance.title}'.",
            },
        )


@receiver(post_save, sender=HelpRequest)
def on_request_completed(sender, instance, created, update_fields, **kwargs):
    """Notify the accepted volunteer when a help request is marked as completed."""
    # Only react to status updates (not new records) where status became 'completed'
    if created:
        return

    if instance.status != HelpRequest.Status.COMPLETED:
        return

    # Respect selective saves: skip if update_fields is set but doesn't include 'status'
    if update_fields is not None and "status" not in update_fields:
        return

    # Find the volunteer whose response was accepted for this request
    accepted_response = Response.objects.filter(
        help_request=instance,
        status=Response.Status.ACCEPTED,
    ).first()

    if accepted_response is None:
        # No accepted volunteer — nothing to notify
        return

    Notification.objects.get_or_create(
        user=accepted_response.volunteer,
        type=Notification.Type.REQUEST_COMPLETED,
        related_request=instance,
        defaults={
            "title": "Запит позначено як виконаний",
            "message": f"Дякуємо за допомогу з запитом '{instance.title}'!",
        },
    )


@receiver(post_save, sender=HelpRequest)
def on_request_completed_recipient(sender, instance, created, update_fields, **kwargs):
    """Notify the recipient when their help request is marked as completed."""
    # Only react to status updates, not new records
    if created:
        return

    if instance.status != HelpRequest.Status.COMPLETED:
        return

    # Respect selective saves: skip if update_fields is set but doesn't include 'status'
    if update_fields is not None and "status" not in update_fields:
        return

    Notification.objects.get_or_create(
        user=instance.recipient,
        type=Notification.Type.REQUEST_COMPLETED,
        related_request=instance,
        defaults={
            "title": "Ваш запит виконано",
            "message": f"Дякуємо! Запит '{instance.title}' успішно виконано.",
        },
    )
