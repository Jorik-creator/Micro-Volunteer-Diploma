import secrets

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class VerificationRequest(models.Model):
    """
    Заявка на рівень «Перевірений» (L2). Документи не подаються (ADR 0001):
    модератор вирішує за анкетою, за потреби після відеодзвінка.
    Рядок також створюється при активації коду організації — для історії.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "На розгляді"
        APPROVED = "approved", "Схвалено"
        REJECTED = "rejected", "Відхилено"
        REVOKED = "revoked", "Відкликано"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="verification_requests",
        verbose_name="Користувач",
    )
    status = models.CharField(
        "Статус", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    city = models.CharField("Місто", max_length=100)
    about = models.TextField("Розкажіть про себе", max_length=1500)
    contact_link = models.URLField("Соцмережа або сторінка організації", blank=True)
    organization = models.CharField("Організація", max_length=150, blank=True)
    video_call_ok = models.BooleanField("Можу поспілкуватися коротким відеодзвінком", default=False)
    invite_code = models.ForeignKey(
        "InviteCode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verifications",
        verbose_name="Код організації",
    )
    created_at = models.DateTimeField("Подано", auto_now_add=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Розглянув",
    )
    reviewed_at = models.DateTimeField("Розглянуто", null=True, blank=True)
    decision_reason = models.CharField("Причина рішення", max_length=500, blank=True)

    class Meta:
        verbose_name = "Заявка на перевірку"
        verbose_name_plural = "Заявки на перевірку"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="pending"),
                name="one_pending_verification_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} — {self.get_status_display()}"


def _generate_code():
    # Unambiguous uppercase alphabet: no 0/O, 1/I/L
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


class InviteCode(models.Model):
    """Код партнерської організації, який одразу надає рівень «Перевірений»."""

    code = models.CharField("Код", max_length=20, unique=True, default=_generate_code)
    organization = models.CharField("Організація", max_length=150)
    max_uses = models.PositiveIntegerField("Максимум використань", default=1)
    uses_count = models.PositiveIntegerField("Використано", default=0)
    expires_at = models.DateTimeField("Діє до", null=True, blank=True)
    is_active = models.BooleanField("Активний", default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name="Створив",
    )
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Код організації"
        verbose_name_plural = "Коди організацій"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.organization})"

    @property
    def is_usable(self):
        not_expired = self.expires_at is None or self.expires_at > timezone.now()
        return self.is_active and not_expired and self.uses_count < self.max_uses


class Report(models.Model):
    """Скарга на запит, користувача, оцінку або повідомлення в розмові."""

    class Reason(models.TextChoices):
        FRAUD = "fraud", "Шахрайство або обман"
        UNSAFE = "unsafe", "Небезпечна ситуація"
        OFFENSIVE = "offensive", "Образи чи неприйнятна поведінка"
        SPAM = "spam", "Спам або реклама"
        FALSE_INFO = "false_info", "Неправдива інформація"
        OTHER = "other", "Інше"

    class Status(models.TextChoices):
        OPEN = "open", "Нова"
        RESOLVED = "resolved", "Вжито заходів"
        DISMISSED = "dismissed", "Відхилено"

    reporter = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="reports_made",
        verbose_name="Автор скарги",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    reason = models.CharField("Причина", max_length=15, choices=Reason.choices)
    comment = models.TextField("Коментар", max_length=1000, blank=True)
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField("Подано", auto_now_add=True)
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Розглянув",
    )
    resolved_at = models.DateTimeField("Розглянуто", null=True, blank=True)
    resolution = models.CharField("Рішення", max_length=500, blank=True)

    class Meta:
        verbose_name = "Скарга"
        verbose_name_plural = "Скарги"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["content_type", "object_id"])]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "content_type", "object_id"],
                condition=models.Q(status="open"),
                name="one_open_report_per_target",
            )
        ]

    def __str__(self):
        return f"{self.get_reason_display()} — {self.content_type.model} #{self.object_id}"
