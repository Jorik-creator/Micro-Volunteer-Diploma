from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator


class Category(models.Model):
    name = models.CharField('Назва', max_length=100)
    slug = models.SlugField('URL-ідентифікатор', unique=True)
    icon = models.CharField('CSS-клас іконки', max_length=50, blank=True)
    description = models.TextField('Опис', blank=True)

    class Meta:
        verbose_name = 'Категорія'
        verbose_name_plural = 'Категорії'
        ordering = ['name']

    def __str__(self):
        return self.name


class HelpRequest(models.Model):
    class Urgency(models.TextChoices):
        LOW = 'low', 'Низька'
        MEDIUM = 'medium', 'Середня'
        HIGH = 'high', 'Висока'
        CRITICAL = 'critical', 'Критична'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активний'
        IN_PROGRESS = 'in_progress', 'В процесі'
        COMPLETED = 'completed', 'Виконано'
        CANCELLED = 'cancelled', 'Скасовано'
        EXPIRED = 'expired', 'Прострочено'

    class Duration(models.TextChoices):
        FIFTEEN_MIN = '15min', '15 хвилин'
        THIRTY_MIN = '30min', '30 хвилин'
        ONE_HOUR = '1h', '1 година'
        TWO_HOURS_PLUS = '2h+', '2 години+'

    recipient = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='help_requests',
        verbose_name='Отримувач',
    )
    title = models.CharField('Заголовок', max_length=200)
    description = models.TextField('Опис')
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='help_requests',
        verbose_name='Категорія',
    )
    urgency = models.CharField('Терміновість', max_length=10, choices=Urgency.choices, default=Urgency.MEDIUM)
    status = models.CharField('Статус', max_length=15, choices=Status.choices, default=Status.ACTIVE)
    needed_date = models.DateTimeField('Дата та час допомоги')
    duration = models.CharField('Тривалість', max_length=10, choices=Duration.choices, default=Duration.ONE_HOUR)
    volunteers_needed = models.IntegerField(
        'Кількість волонтерів',
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    address = models.CharField('Адреса', max_length=255)
    latitude = models.FloatField('Широта', null=True, blank=True)
    longitude = models.FloatField('Довгота', null=True, blank=True)
    photo = models.ImageField(
        'Фото',
        upload_to='requests/',
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
    )
    created_at = models.DateTimeField('Дата створення', auto_now_add=True)
    updated_at = models.DateTimeField('Дата оновлення', auto_now=True)

    class Meta:
        verbose_name = 'Запит допомоги'
        verbose_name_plural = 'Запити допомоги'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class Response(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Очікує'
        ACCEPTED = 'accepted', 'Прийнято'
        REJECTED = 'rejected', 'Відхилено'

    help_request = models.ForeignKey(
        HelpRequest,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Запит',
    )
    volunteer = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='volunteer_responses',
        verbose_name='Волонтер',
    )
    status = models.CharField('Статус', max_length=10, choices=Status.choices, default=Status.PENDING)
    message = models.TextField('Повідомлення', blank=True)
    created_at = models.DateTimeField('Дата відгуку', auto_now_add=True)

    class Meta:
        verbose_name = 'Відгук волонтера'
        verbose_name_plural = 'Відгуки волонтерів'
        ordering = ['-created_at']
        unique_together = ['help_request', 'volunteer']

    def __str__(self):
        return f"{self.volunteer} → {self.help_request.title} ({self.get_status_display()})"
