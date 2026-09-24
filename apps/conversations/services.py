"""
Conversations between a recipient and an accepted volunteer (docs/adr/0007).

- opened automatically when a volunteer is accepted;
- plain text only, links are never rendered clickable (anti-phishing);
- phone numbers are shared only by an explicit button press;
- the other side is notified at most once per NOTIFY_EVERY per conversation.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import notify

from .models import Conversation, Message

MAX_LENGTH = 1000
NOTIFY_EVERY = timedelta(minutes=10)
RATE_LIMIT = 30  # messages per RATE_WINDOW per sender and conversation
RATE_WINDOW = timedelta(minutes=10)


class ConversationError(Exception):
    """The message cannot be sent."""


def _name(user):
    return user.get_full_name() or user.username


def open_for(response):
    """Create (or reopen) the conversation when a volunteer is accepted."""
    conversation, created = Conversation.objects.get_or_create(
        help_request=response.help_request,
        volunteer=response.volunteer,
        defaults={"recipient": response.help_request.recipient},
    )
    if created:
        _system(
            conversation,
            "Волонтера прийнято. Тут можна домовитися про деталі. "
            "Номери телефонів приховані — поділіться своїм кнопкою, якщо потрібно.",
        )
    return conversation


def _system(conversation, text):
    message = Message.objects.create(conversation=conversation, kind=Message.Kind.SYSTEM, body=text)
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=message.created_at)
    return message


def _notify_other(conversation, sender, preview):
    other = conversation.other(sender)
    side = "recipient" if other.pk == conversation.recipient_id else "volunteer"
    notified_field = f"{side}_notified_at"
    now = timezone.now()
    last = getattr(conversation, notified_field)
    if last and now - last < NOTIFY_EVERY:
        return
    # Conditional update: two quick messages cannot both notify
    updated = Conversation.objects.filter(
        Q(**{f"{notified_field}__isnull": True})
        | Q(**{f"{notified_field}__lt": now - NOTIFY_EVERY}),
        pk=conversation.pk,
    ).update(**{notified_field: now})
    if updated:
        notify(
            other,
            Notification.Type.NEW_MESSAGE,
            f"Нове повідомлення від {_name(sender)}",
            f"Запит «{conversation.help_request.title}»: {preview[:120]}",
            conversation.help_request,
            link=reverse("conversations:detail", args=[conversation.pk]),
        )


@transaction.atomic
def send(conversation, sender, body, kind=Message.Kind.TEXT):
    body = (body or "").strip()
    if not conversation.is_participant(sender):
        raise ConversationError("Це не ваша розмова.")
    if not conversation.is_writable:
        raise ConversationError("Розмову закрито — запит завершено або волонтер вийшов.")
    if not body:
        raise ConversationError("Повідомлення порожнє.")
    if len(body) > MAX_LENGTH:
        raise ConversationError(f"Повідомлення задовге (максимум {MAX_LENGTH} символів).")
    recent = conversation.messages.filter(
        sender=sender, created_at__gte=timezone.now() - RATE_WINDOW
    ).count()
    if recent >= RATE_LIMIT:
        raise ConversationError("Забагато повідомлень поспіль — зачекайте кілька хвилин.")

    message = Message.objects.create(conversation=conversation, sender=sender, kind=kind, body=body)
    side = "recipient" if sender.pk == conversation.recipient_id else "volunteer"
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=message.created_at, **{f"{side}_read_at": message.created_at}
    )
    _notify_other(
        conversation,
        sender,
        body if kind == Message.Kind.TEXT else "надіслано номер телефону",
    )
    return message


def share_phone(conversation, user):
    if not user.phone:
        raise ConversationError("Спершу додайте номер телефону в профілі.")
    already = conversation.messages.filter(sender=user, kind=Message.Kind.PHONE).exists()
    if already:
        raise ConversationError("Ви вже поділилися номером у цій розмові.")
    return send(conversation, user, user.phone, kind=Message.Kind.PHONE)


def visible_messages(conversation, after_id=0):
    return (
        conversation.messages.filter(pk__gt=after_id, hidden_at__isnull=True)
        .select_related("sender")
        .order_by("created_at", "id")
    )


def conversations_for(user):
    return (
        Conversation.objects.filter(Q(recipient=user) | Q(volunteer=user))
        .select_related("help_request", "recipient", "volunteer")
        .order_by(F("last_message_at").desc(nulls_last=True), "-created_at")
    )


def unread_count(user):
    unread = (
        Conversation.objects.filter(
            Q(recipient=user, last_message_at__gt=F("recipient_read_at"))
            | Q(recipient=user, recipient_read_at__isnull=True, last_message_at__isnull=False)
            | Q(volunteer=user, last_message_at__gt=F("volunteer_read_at"))
            | Q(volunteer=user, volunteer_read_at__isnull=True, last_message_at__isnull=False)
        )
        .select_related("help_request")
        .distinct()
    )
    # Archived ones are hidden from the list, so they must not light up the badge
    return sum(1 for conversation in unread if not conversation.is_archived)


def serialize(message, viewer):
    return {
        "id": message.pk,
        "kind": message.kind,
        "body": message.body,
        "mine": message.sender_id == viewer.pk,
        "sender": message.sender.first_name if message.sender else "",
        "time": timezone.localtime(message.created_at).strftime("%d.%m %H:%M"),
    }
