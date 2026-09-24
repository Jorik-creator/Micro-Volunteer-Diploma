from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ReviewQuerySet(models.QuerySet):
    def published(self):
        """Visible reviews: exchange finished and not hidden by a moderator."""
        return self.filter(published_at__isnull=False, hidden_at__isnull=True)


class Review(models.Model):
    """
    Оцінка однієї сторони запиту іншою після його завершення.

    Двостороння і прихована (docs/adr/0006): стає видимою лише коли обидві
    сторони пари залишили свої оцінки або минуло вікно оцінювання.
    """

    class Tag(models.TextChoices):
        # About a volunteer
        PUNCTUAL = "punctual", "Пунктуальність"
        POLITE = "polite", "Ввічливість"
        CAREFUL = "careful", "Дбайливість"
        IN_TOUCH = "in_touch", "На зв'язку"
        LATE = "late", "Запізнення"
        NO_SHOW = "no_show", "Неявка на зустріч"
        # About a recipient
        CLEAR_REQUEST = "clear_request", "Чіткий опис запиту"
        WELCOMING = "welcoming", "Привітність"
        ON_TIME = "on_time", "Вчасно на місці"
        WRONG_INFO = "wrong_info", "Неточна інформація"
        UNREACHABLE = "unreachable", "Не було зв'язку"

    VOLUNTEER_TAGS = (Tag.PUNCTUAL, Tag.POLITE, Tag.CAREFUL, Tag.IN_TOUCH, Tag.LATE, Tag.NO_SHOW)
    RECIPIENT_TAGS = (
        Tag.CLEAR_REQUEST,
        Tag.WELCOMING,
        Tag.ON_TIME,
        Tag.WRONG_INFO,
        Tag.UNREACHABLE,
    )
    NEGATIVE_TAGS = (Tag.LATE, Tag.NO_SHOW, Tag.WRONG_INFO, Tag.UNREACHABLE)

    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="reviews_written",
        verbose_name="Автор",
    )
    target = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="reviews_received",
        verbose_name="Про кого",
    )
    help_request = models.ForeignKey(
        "requests.HelpRequest",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Запит допомоги",
    )
    rating = models.IntegerField(
        "Оцінка",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    tags = models.JSONField("Теги", default=list, blank=True)
    comment = models.TextField("Коментар", blank=True, max_length=1000)
    created_at = models.DateTimeField("Дата створення", auto_now_add=True)
    published_at = models.DateTimeField("Опубліковано", null=True, blank=True)
    hidden_at = models.DateTimeField("Приховано модератором", null=True, blank=True)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        verbose_name = "Оцінка"
        verbose_name_plural = "Оцінки"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["author", "target", "help_request"], name="one_review_per_pair"
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5), name="rating_1_to_5"
            ),
        ]

    def __str__(self):
        return f"{self.author} → {self.target}: {self.rating}/5"

    @property
    def is_published(self):
        return self.published_at is not None

    def get_tags_display(self):
        labels = dict(self.Tag.choices)
        return [labels[tag] for tag in self.tags if tag in labels]
