"""
Two-sided blind reviews (docs/adr/0006).

After a request is completed, the recipient and every volunteer who was
accepted at that moment form pairs. Each side of a pair may rate the other
once within REVIEW_WINDOW. A review stays hidden until the counterpart has
rated back or the window closes, so nobody adjusts their rating in reaction.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.requests.models import HelpRequest, Response

from .models import Review

REVIEW_WINDOW = timedelta(days=14)
REMIND_AFTER = timedelta(days=3)


class ReviewError(Exception):
    """The user may not leave this review."""


def _name(user):
    return user.get_full_name() or user.username


def review_deadline(help_request):
    return help_request.completed_at + REVIEW_WINDOW


def counterparts(help_request, user):
    """Users that `user` may rate on this request (empty when not a participant)."""
    if help_request.status != HelpRequest.Status.COMPLETED or help_request.completed_at is None:
        return []
    accepted = [
        r.volunteer
        for r in help_request.responses.filter(status=Response.Status.ACCEPTED).select_related(
            "volunteer"
        )
    ]
    if user.pk == help_request.recipient_id:
        return accepted
    if any(v.pk == user.pk for v in accepted):
        return [help_request.recipient]
    return []


def review_error(author, help_request, target, now=None):
    """Why `author` cannot rate `target` on this request, or None if they can."""
    now = now or timezone.now()
    if help_request.status != HelpRequest.Status.COMPLETED:
        return "Оцінити можна лише після завершення запиту."
    if not any(u.pk == target.pk for u in counterparts(help_request, author)):
        return "Ви не можете оцінити цього користувача за цим запитом."
    if now > review_deadline(help_request):
        return "Час для оцінки минув (14 днів після завершення)."
    if Review.objects.filter(author=author, target=target, help_request=help_request).exists():
        return "Ви вже оцінили цього користувача за цим запитом."
    return None


def allowed_tags(target):
    return Review.VOLUNTEER_TAGS if target.is_volunteer else Review.RECIPIENT_TAGS


def _publish(reviews, now):
    for review in reviews:
        review.published_at = now
        review.save(update_fields=["published_at"])
        notify(
            review.target,
            Notification.Type.NEW_REVIEW,
            "Нова оцінка про вас",
            f"{_name(review.author)} оцінив(ла) вас на {review.rating}/5 "
            f"за запитом «{review.help_request.title}».",
            review.help_request,
        )


@transaction.atomic
def submit_review(author, help_request, target, rating, tags=(), comment=""):
    now = timezone.now()
    error = review_error(author, help_request, target, now)
    if error:
        raise ReviewError(error)
    tags = [tag for tag in tags if tag in allowed_tags(target)]
    try:
        with transaction.atomic():
            review = Review.objects.create(
                author=author,
                target=target,
                help_request=help_request,
                rating=rating,
                tags=tags,
                comment=comment.strip(),
            )
    except IntegrityError as exc:  # double submit racing the check above
        raise ReviewError("Ви вже оцінили цього користувача за цим запитом.") from exc

    counterpart = Review.objects.filter(
        author=target, target=author, help_request=help_request, published_at__isnull=True
    ).first()
    if counterpart:
        _publish([review, counterpart], now)
    else:
        notify(
            target,
            Notification.Type.REMINDER,
            "Вас оцінили — оцініть і ви",
            f"{_name(author)} залишив(ла) оцінку за запитом «{help_request.title}». "
            "Вона стане видимою, щойно ви залишите свою, або через 14 днів.",
            help_request,
        )
    return review


def publish_due(now=None):
    """Publish reviews whose window closed without a counterpart review."""
    now = now or timezone.now()
    due = list(
        Review.objects.filter(
            published_at__isnull=True,
            help_request__completed_at__lt=now - REVIEW_WINDOW,
        ).select_related("author", "target", "help_request")
    )
    _publish(due, now)
    return len(due)


def pending_reviews(user, now=None):
    """
    (help_request, target) pairs the user can still rate, newest first.
    Used for reminders and for the "rate now" prompts.
    """
    now = now or timezone.now()
    requests = (
        HelpRequest.objects.filter(
            status=HelpRequest.Status.COMPLETED,
            completed_at__gte=now - REVIEW_WINDOW,
        )
        .filter(
            Q(recipient=user)
            | Q(responses__volunteer=user, responses__status=Response.Status.ACCEPTED)
        )
        .distinct()
        .order_by("-completed_at")
    )
    written = set(
        Review.objects.filter(author=user, help_request__in=requests).values_list(
            "help_request_id", "target_id"
        )
    )
    return [
        (help_request, target)
        for help_request in requests
        for target in counterparts(help_request, user)
        if (help_request.pk, target.pk) not in written
    ]


def send_review_reminders(now=None):
    """One reminder per request and person, three days after completion."""
    now = now or timezone.now()
    sent = 0
    completed = HelpRequest.objects.filter(
        status=HelpRequest.Status.COMPLETED,
        completed_at__lt=now - REMIND_AFTER,
        completed_at__gte=now - REVIEW_WINDOW,
    ).select_related("recipient")
    for help_request in completed:
        participants = [help_request.recipient] + [
            r.volunteer
            for r in help_request.responses.filter(status=Response.Status.ACCEPTED).select_related(
                "volunteer"
            )
        ]
        already = set(
            Notification.objects.filter(
                related_request=help_request, type=Notification.Type.REVIEW_REMINDER
            ).values_list("user_id", flat=True)
        )
        written = set(help_request.reviews.values_list("author_id", "target_id"))
        for user in participants:
            if user.pk in already:
                continue
            missing = [
                t for t in counterparts(help_request, user) if (user.pk, t.pk) not in written
            ]
            if not missing:
                continue
            notify(
                user,
                Notification.Type.REVIEW_REMINDER,
                "Залиште оцінку",
                f"Як усе пройшло із запитом «{help_request.title}»? "
                "Ваша оцінка допомагає іншим обирати надійних людей.",
                help_request,
            )
            sent += 1
    return sent


def rating_summary(user):
    """Average rating, count and most frequent tags from published reviews."""
    published = Review.objects.published().filter(target=user)
    stats = published.aggregate(avg=Avg("rating"), count=Count("pk"))
    tag_counts = {}
    for tags in published.values_list("tags", flat=True):
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    labels = dict(Review.Tag.choices)
    top_tags = [
        {"label": labels[tag], "count": count, "negative": tag in Review.NEGATIVE_TAGS}
        for tag, count in sorted(tag_counts.items(), key=lambda item: -item[1])
        if tag in labels
    ]
    return RatingSummary(
        average=round(stats["avg"], 1) if stats["avg"] is not None else None,
        count=stats["count"],
        top_tags=top_tags[:6],
    )


@dataclass
class RatingSummary:
    average: float | None
    count: int
    top_tags: list
