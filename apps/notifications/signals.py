from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications.models import Notification
from apps.reviews.models import Review


@receiver(post_save, sender=Review)
def on_review_created(sender, instance, created, **kwargs):
    """Notify the review target when a new review is posted about them."""
    if not created:
        return

    review = instance
    author = review.author.get_full_name() or review.author.username
    Notification.objects.get_or_create(
        user=review.target,
        type=Notification.Type.NEW_REVIEW,
        related_request=review.help_request,
        defaults={
            "title": f"{author} залишив(ла) відгук про вас",
            "message": f"Оцінка: {review.rating}/5. {review.comment[:100]}",
        },
    )
