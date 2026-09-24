from datetime import timedelta

from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField("Назва", max_length=100)
    slug = models.SlugField("URL-ідентифікатор", unique=True)
    icon = models.CharField("CSS-клас іконки", max_length=50, blank=True)
    description = models.TextField("Опис", blank=True)

    class Meta:
        verbose_name = "Категорія"
        verbose_name_plural = "Категорії"
        ordering = ["name"]

    def __str__(self):
        return self.name


class HelpRequestQuerySet(models.QuerySet):
    def ordered_by_urgency(self):
        """Most urgent first (critical → low), then the soonest date."""
        rank = models.Case(
            *(
                models.When(urgency=value, then=models.Value(position))
                for position, value in enumerate(reversed(HelpRequest.Urgency.values))
            ),
            output_field=models.IntegerField(),
        )
        return self.annotate(urgency_rank=rank).order_by("urgency_rank", "needed_date")

    def visible_to(self, user):
        """
        Requests the user may open: every active request, plus any request
        they own or have responded to. Non-active requests of other people
        stay hidden so their existence cannot be probed by pk.
        """
        visible = models.Q(status=HelpRequest.Status.ACTIVE)
        if user.is_authenticated:
            visible |= models.Q(recipient=user) | models.Q(responses__volunteer=user)
        return self.filter(visible).distinct()


class HelpRequest(models.Model):
    class Urgency(models.TextChoices):
        LOW = "low", "Низька"
        MEDIUM = "medium", "Середня"
        HIGH = "high", "Висока"
        CRITICAL = "critical", "Критична"

    class Status(models.TextChoices):
        DRAFT = "draft", "Чернетка"
        PENDING_MODERATION = "pending_moderation", "На модерації"
        REJECTED = "rejected", "Відхилено модератором"
        ACTIVE = "active", "Активний"
        IN_PROGRESS = "in_progress", "В процесі"
        AWAITING_CONFIRMATION = "awaiting_confirmation", "Очікує підтвердження"
        COMPLETED = "completed", "Виконано"
        CANCELLED = "cancelled", "Скасовано"
        EXPIRED = "expired", "Прострочено"

    class Duration(models.TextChoices):
        FIFTEEN_MIN = "15min", "15 хвилин"
        THIRTY_MIN = "30min", "30 хвилин"
        ONE_HOUR = "1h", "1 година"
        TWO_HOURS_PLUS = "2h+", "2 години+"

    class HelpFormat(models.TextChoices):
        HOME_VISIT = "home_visit", "Візит додому"
        DOORSTEP = "doorstep", "Під двері"
        PUBLIC_PLACE = "public_place", "Зустріч у публічному місці"
        REMOTE = "remote", "Онлайн або телефоном"

    HELP_FORMAT_HINTS = {
        HelpFormat.HOME_VISIT: "Волонтер заходить до оселі: прибирання, дрібний ремонт, допомога по дому.",
        HelpFormat.DOORSTEP: "Доставка продуктів чи ліків до дверей, без входу в оселю.",
        HelpFormat.PUBLIC_PLACE: "Супровід до лікаря, у ЦНАП, на пошту.",
        HelpFormat.REMOTE: "Консультація, допомога з Дією чи формами — без зустрічі.",
    }

    DURATION_DELTAS = {
        Duration.FIFTEEN_MIN: timedelta(minutes=15),
        Duration.THIRTY_MIN: timedelta(minutes=30),
        Duration.ONE_HOUR: timedelta(hours=1),
        Duration.TWO_HOURS_PLUS: timedelta(hours=2),
    }

    OPEN_STATUSES = (Status.ACTIVE, Status.IN_PROGRESS, Status.AWAITING_CONFIRMATION)

    recipient = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="help_requests",
        verbose_name="Отримувач",
    )
    title = models.CharField("Заголовок", max_length=200)
    description = models.TextField("Опис")
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name="help_requests",
        verbose_name="Категорія",
    )
    urgency = models.CharField(
        "Терміновість", max_length=10, choices=Urgency.choices, default=Urgency.MEDIUM
    )
    status = models.CharField(
        "Статус", max_length=25, choices=Status.choices, default=Status.ACTIVE
    )
    needed_date = models.DateTimeField("Дата та час допомоги")
    duration = models.CharField(
        "Тривалість", max_length=10, choices=Duration.choices, default=Duration.ONE_HOUR
    )
    # Existing requests default to the strictest format (home visit needs L2)
    help_format = models.CharField(
        "Формат допомоги",
        max_length=15,
        choices=HelpFormat.choices,
        default=HelpFormat.HOME_VISIT,
    )
    volunteers_needed = models.IntegerField(
        "Кількість волонтерів",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    address = models.CharField("Адреса", max_length=255, blank=True)
    latitude = models.FloatField(
        "Широта", null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.FloatField(
        "Довгота",
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    photo = models.ImageField(
        "Фото",
        upload_to="requests/",
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
    )
    created_at = models.DateTimeField("Дата створення", auto_now_add=True)
    updated_at = models.DateTimeField("Дата оновлення", auto_now=True)
    status_changed_at = models.DateTimeField("Статус змінено", default=timezone.now)
    completed_at = models.DateTimeField("Дата завершення", null=True, blank=True)
    published_at = models.DateTimeField("Опубліковано", null=True, blank=True)
    moderation_note = models.CharField("Коментар модератора", max_length=300, blank=True)
    reminder_sent_at = models.DateTimeField("Нагадування надіслано", null=True, blank=True)

    objects = HelpRequestQuerySet.as_manager()

    class Meta:
        verbose_name = "Запит допомоги"
        verbose_name_plural = "Запити допомоги"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "needed_date"])]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    @property
    def ends_at(self):
        """When the help is expected to be over."""
        return self.needed_date + self.DURATION_DELTAS.get(self.duration, timedelta(hours=1))

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def needs_verified_volunteer(self):
        return self.help_format == self.HelpFormat.HOME_VISIT

    @property
    def is_remote(self):
        return self.help_format == self.HelpFormat.REMOTE

    @property
    def is_editable(self):
        return self.status in (
            self.Status.DRAFT,
            self.Status.PENDING_MODERATION,
            self.Status.ACTIVE,
        )

    def accepted_responses(self):
        return self.responses.filter(status=Response.Status.ACCEPTED)


class Response(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Очікує"
        ACCEPTED = "accepted", "Прийнято"
        REJECTED = "rejected", "Відхилено"
        WITHDRAWN = "withdrawn", "Волонтер вийшов"
        REMOVED = "removed", "Знято отримувачем"
        CLOSED = "closed", "Набір закрито"

    help_request = models.ForeignKey(
        HelpRequest,
        on_delete=models.CASCADE,
        related_name="responses",
        verbose_name="Запит",
    )
    volunteer = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="volunteer_responses",
        verbose_name="Волонтер",
    )
    status = models.CharField(
        "Статус", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    message = models.TextField("Повідомлення", blank=True)
    status_reason = models.CharField("Причина зміни статусу", max_length=300, blank=True)
    done_at = models.DateTimeField("Позначено виконаним", null=True, blank=True)
    created_at = models.DateTimeField("Дата відгуку", auto_now_add=True)

    class Meta:
        verbose_name = "Відгук волонтера"
        verbose_name_plural = "Відгуки волонтерів"
        ordering = ["-created_at"]
        unique_together = ["help_request", "volunteer"]

    def __str__(self):
        return f"{self.volunteer} → {self.help_request.title} ({self.get_status_display()})"
