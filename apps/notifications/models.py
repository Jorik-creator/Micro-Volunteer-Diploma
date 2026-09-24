from django.db import models


class Notification(models.Model):
    """Внутрішнє сповіщення для користувача."""

    class Type(models.TextChoices):
        # To the recipient
        NEW_RESPONSE = "new_response", "Новий відгук волонтера"
        VOLUNTEER_WITHDREW = "volunteer_withdrew", "Волонтер вийшов"
        MARKED_DONE = "marked_done", "Волонтер позначив виконаним"
        # To the volunteer
        REQUEST_ACCEPTED = "request_accepted", "Вас прийнято"
        REQUEST_REJECTED = "request_rejected", "Відгук відхилено"
        RESPONSE_CLOSED = "response_closed", "Набір закрито"
        VOLUNTEER_REMOVED = "volunteer_removed", "Вас знято із запиту"
        COMPLETION_DISPUTED = "completion_disputed", "Виконання не підтверджено"
        NEW_NEARBY_REQUEST = "new_nearby_request", "Новий запит поблизу"
        # To both sides
        REQUEST_COMPLETED = "request_completed", "Запит виконано"
        REQUEST_CANCELLED = "request_cancelled", "Запит скасовано"
        REQUEST_EXPIRED = "request_expired", "Запит прострочено"
        REMINDER = "reminder", "Нагадування"
        NEW_REVIEW = "new_review", "Нова оцінка"
        REVIEW_REMINDER = "review_reminder", "Нагадування про оцінку"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Користувач",
    )
    type = models.CharField("Тип", max_length=25, choices=Type.choices)
    title = models.CharField("Заголовок", max_length=200)
    message = models.TextField("Текст")
    related_request = models.ForeignKey(
        "requests.HelpRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="Пов'язаний запит",
    )
    is_read = models.BooleanField("Прочитано", default=False)
    created_at = models.DateTimeField("Дата створення", auto_now_add=True)

    class Meta:
        verbose_name = "Сповіщення"
        verbose_name_plural = "Сповіщення"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        status = "✓" if self.is_read else "●"
        return f"{status} {self.title} → {self.user}"
