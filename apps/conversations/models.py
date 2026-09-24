from datetime import timedelta

from django.db import models
from django.utils import timezone

READ_ONLY_FOR = timedelta(days=14)


class Conversation(models.Model):
    """
    Приватна розмова отримувача з одним прийнятим волонтером у межах запиту
    (docs/adr/0007). Відкривається при прийнятті волонтера.
    """

    help_request = models.ForeignKey(
        "requests.HelpRequest",
        on_delete=models.CASCADE,
        related_name="conversations",
        verbose_name="Запит",
    )
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="+", verbose_name="Отримувач"
    )
    volunteer = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="+", verbose_name="Волонтер"
    )
    created_at = models.DateTimeField("Створено", auto_now_add=True)
    last_message_at = models.DateTimeField("Останнє повідомлення", null=True, blank=True)
    recipient_read_at = models.DateTimeField(null=True, blank=True)
    volunteer_read_at = models.DateTimeField(null=True, blank=True)
    recipient_notified_at = models.DateTimeField(null=True, blank=True)
    volunteer_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Розмова"
        verbose_name_plural = "Розмови"
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["help_request", "volunteer"], name="one_conversation_per_volunteer"
            )
        ]

    def __str__(self):
        return f"{self.help_request.title}: {self.recipient} ↔ {self.volunteer}"

    def is_participant(self, user):
        return user.pk in (self.recipient_id, self.volunteer_id)

    def other(self, user):
        return self.volunteer if user.pk == self.recipient_id else self.recipient

    def _side(self, user):
        return "recipient" if user.pk == self.recipient_id else "volunteer"

    def read_at(self, user):
        return getattr(self, f"{self._side(user)}_read_at")

    def mark_read(self, user):
        field = f"{self._side(user)}_read_at"
        setattr(self, field, timezone.now())
        self.save(update_fields=[field])

    def has_unread(self, user):
        read_at = self.read_at(user)
        return bool(self.last_message_at) and (read_at is None or read_at < self.last_message_at)

    @property
    def response(self):
        return self.help_request.responses.filter(volunteer_id=self.volunteer_id).first()

    @property
    def is_writable(self):
        """Open while the volunteer is still accepted on an open request."""
        return self._writable(self.response)

    def _writable(self, response):
        from apps.requests.models import Response

        return (
            self.help_request.is_open
            and response is not None
            and response.status == Response.Status.ACCEPTED
        )

    @property
    def closed_since(self):
        """
        When the conversation became read-only (None while writable): the
        volunteer leaving and/or the request closing, whichever came last.
        """
        from apps.requests.models import Response

        response = self.response
        if self._writable(response):
            return None
        moments = []
        if response is not None and response.status != Response.Status.ACCEPTED:
            moments.append(response.status_changed_at)
        if not self.help_request.is_open or not moments:
            moments.append(self.help_request.status_changed_at)
        return max(moments)

    @property
    def is_archived(self):
        closed = self.closed_since
        return closed is not None and timezone.now() > closed + READ_ONLY_FOR


class Message(models.Model):
    class Kind(models.TextChoices):
        TEXT = "text", "Повідомлення"
        PHONE = "phone", "Номер телефону"
        SYSTEM = "system", "Системне"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages", verbose_name="Розмова"
    )
    sender = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Автор",
    )
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.TEXT)
    body = models.TextField("Текст", max_length=1000)
    created_at = models.DateTimeField("Надіслано", auto_now_add=True)
    hidden_at = models.DateTimeField("Приховано модератором", null=True, blank=True)

    # Used by the moderation queue for reports on messages
    moderation_measure = "Приховати повідомлення"

    class Meta:
        verbose_name = "Повідомлення"
        verbose_name_plural = "Повідомлення"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"«{self.body[:80]}»"

    def hide(self):
        self.hidden_at = timezone.now()
        self.save(update_fields=["hidden_at"])
