from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications.models import Notification
from apps.reviews.models import Review
from apps.requests.models import HelpRequest, Response


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
            "title": f"{review.author.get_full_name()} залишив(ла) відгук про вас",
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

    if instance.status == Response.Status.ACCEPTED:
        # W1 fix: "отримувачем" (recipient accepts), not "волонтером"
        Notification.objects.get_or_create(
            user=instance.volunteer,
            type=Notification.Type.REQUEST_ACCEPTED,
            related_request=instance.help_request,
            defaults={
                "title": "Вас підтверджено як волонтера",
                "message": f"Запит '{instance.help_request.title}' тепер в роботі",
            },
        )

    elif instance.status == Response.Status.REJECTED:
        # W8: повідомляємо волонтера про відхилення
        Notification.objects.get_or_create(
            user=instance.volunteer,
            type=Notification.Type.REQUEST_REJECTED,
            related_request=instance.help_request,
            defaults={
                "title": "Ваш відгук не прийнято",
                "message": (
                    f"На жаль, ваш відгук на запит "
                    f"'{instance.help_request.title}' відхилено."
                ),
            },
        )


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
            "title": f"{instance.volunteer.get_full_name()} відгукнувся(лась) на ваш запит",
            "message": (
                f"Запит: '{instance.help_request.title}'. "
                "Перегляньте відгуки та оберіть волонтера."
            ),
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
