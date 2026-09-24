from django.db import models
from django.urls import reverse


class Notification(models.Model):
    """Внутрішнє сповіщення для користувача."""

    class Type(models.TextChoices):
        # To the recipient
        NEW_RESPONSE = "new_response", "Новий відгук волонтера"
        VOLUNTEER_WITHDREW = "volunteer_withdrew", "Волонтер вийшов"
        MARKED_DONE = "marked_done", "Волонтер позначив виконаним"
        REQUEST_APPROVED = "request_approved", "Запит опубліковано"
        REQUEST_REJECTED_BY_MODERATOR = "request_moderated", "Запит не пройшов модерацію"
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
        NEW_MESSAGE = "new_message", "Нове повідомлення"
        NEW_REVIEW = "new_review", "Нова оцінка"
        VERIFICATION_DECISION = "verification", "Рішення щодо перевірки"
        REPORT_RESOLVED = "report_resolved", "Скаргу розглянуто"
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
    # Where the next step happens when it is not the request page (e.g. a conversation)
    link = models.CharField("Посилання", max_length=300, blank=True)
    is_read = models.BooleanField("Прочитано", default=False)
    created_at = models.DateTimeField("Дата створення", auto_now_add=True)

    class Meta:
        verbose_name = "Сповіщення"
        verbose_name_plural = "Сповіщення"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        status = "✓" if self.is_read else "●"
        return f"{status} {self.title} → {self.user}"

    @property
    def url(self):
        """Site-relative URL of the page where the user acts on this notification."""
        if self.link:
            return self.link
        if self.related_request_id:
            return reverse("requests:detail", args=[self.related_request_id])
        return reverse("notifications:notification-list")


class EmailPreferences(models.Model):
    """Which notification groups are also sent by email (ROADMAP stage 6)."""

    class Group(models.TextChoices):
        RESPONSES = "responses", "Відгуки волонтерів і рішення щодо них"
        LIFECYCLE = "lifecycle", "Зміни запиту: виконано, скасовано, нагадування"
        MESSAGES = "messages", "Нові повідомлення в розмовах"
        REVIEWS = "reviews", "Оцінки"
        NEARBY = "nearby", "Нові запити поблизу"
        ACCOUNT = "account", "Перевірка профілю та рішення модераторів"

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="email_preferences",
        verbose_name="Користувач",
    )
    responses = models.BooleanField(Group.RESPONSES.label, default=True)
    lifecycle = models.BooleanField(Group.LIFECYCLE.label, default=True)
    messages = models.BooleanField(Group.MESSAGES.label, default=True)
    reviews = models.BooleanField(Group.REVIEWS.label, default=True)
    # Can be many per day — opt-in
    nearby = models.BooleanField(Group.NEARBY.label, default=False)
    account = models.BooleanField(Group.ACCOUNT.label, default=True)

    class Meta:
        verbose_name = "Налаштування email"
        verbose_name_plural = "Налаштування email"

    def __str__(self):
        return f"Email: {self.user}"

    def wants(self, group):
        return getattr(self, group, False)


T = Notification.Type
EMAIL_GROUPS = {
    T.NEW_RESPONSE: EmailPreferences.Group.RESPONSES,
    T.REQUEST_ACCEPTED: EmailPreferences.Group.RESPONSES,
    T.REQUEST_REJECTED: EmailPreferences.Group.RESPONSES,
    T.RESPONSE_CLOSED: EmailPreferences.Group.RESPONSES,
    T.VOLUNTEER_WITHDREW: EmailPreferences.Group.LIFECYCLE,
    T.VOLUNTEER_REMOVED: EmailPreferences.Group.LIFECYCLE,
    T.MARKED_DONE: EmailPreferences.Group.LIFECYCLE,
    T.COMPLETION_DISPUTED: EmailPreferences.Group.LIFECYCLE,
    T.REQUEST_COMPLETED: EmailPreferences.Group.LIFECYCLE,
    T.REQUEST_CANCELLED: EmailPreferences.Group.LIFECYCLE,
    T.REQUEST_EXPIRED: EmailPreferences.Group.LIFECYCLE,
    T.REMINDER: EmailPreferences.Group.LIFECYCLE,
    T.NEW_MESSAGE: EmailPreferences.Group.MESSAGES,
    T.NEW_REVIEW: EmailPreferences.Group.REVIEWS,
    T.REVIEW_REMINDER: EmailPreferences.Group.REVIEWS,
    T.NEW_NEARBY_REQUEST: EmailPreferences.Group.NEARBY,
    T.REQUEST_APPROVED: EmailPreferences.Group.ACCOUNT,
    T.REQUEST_REJECTED_BY_MODERATOR: EmailPreferences.Group.ACCOUNT,
    T.VERIFICATION_DECISION: EmailPreferences.Group.ACCOUNT,
    T.REPORT_RESOLVED: EmailPreferences.Group.ACCOUNT,
}
