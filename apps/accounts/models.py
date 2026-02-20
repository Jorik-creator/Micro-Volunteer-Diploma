from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator
from django.db import models


class User(AbstractUser):
    """Custom user model with volunteer/recipient role distinction."""

    class UserType(models.TextChoices):
        VOLUNTEER = 'volunteer', 'Волонтер'
        RECIPIENT = 'recipient', 'Отримувач допомоги'

    email = models.EmailField('Електронна пошта', unique=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    user_type = models.CharField(
        'Тип акаунту',
        max_length=10,
        choices=UserType.choices,
    )
    address = models.CharField('Адреса', max_length=255, blank=True)
    latitude = models.FloatField('Широта', null=True, blank=True)
    longitude = models.FloatField('Довгота', null=True, blank=True)
    date_of_birth = models.DateField('Дата народження', null=True, blank=True)
    avatar = models.ImageField(
        'Фото профілю',
        upload_to='avatars/',
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
            )
        ],
    )
    is_verified = models.BooleanField('Верифікований', default=False)
    created_at = models.DateTimeField('Дата реєстрації', auto_now_add=True)

    class Meta:
        verbose_name = 'Користувач'
        verbose_name_plural = 'Користувачі'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_user_type_display()})"

    @property
    def is_volunteer(self):
        return self.user_type == self.UserType.VOLUNTEER

    @property
    def is_recipient(self):
        return self.user_type == self.UserType.RECIPIENT


class VolunteerProfile(models.Model):
    """Extended profile for volunteer users."""

    class RadiusChoices(models.IntegerChoices):
        SMALL = 5, '5 км'
        MEDIUM = 10, '10 км'
        LARGE = 20, '20 км'

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='volunteer_profile',
        verbose_name='Користувач',
    )
    categories = models.ManyToManyField(
        'requests.Category',
        blank=True,
        related_name='volunteers',
        verbose_name='Категорії допомоги',
    )
    radius_km = models.IntegerField(
        'Радіус готовності',
        choices=RadiusChoices.choices,
        default=RadiusChoices.MEDIUM,
    )
    is_available = models.BooleanField('Доступний', default=True)
    bio = models.TextField('Про себе', blank=True)

    class Meta:
        verbose_name = 'Профіль волонтера'
        verbose_name_plural = 'Профілі волонтерів'

    def __str__(self):
        return f"Профіль волонтера: {self.user.get_full_name()}"


class RecipientProfile(models.Model):
    """Extended profile for help-recipient users."""

    class SituationType(models.TextChoices):
        ELDERLY = 'elderly', 'Літня людина'
        DISABILITY = 'disability', 'Особа з інвалідністю'
        LARGE_FAMILY = 'large_family', 'Багатодітна сім\'я'
        IDP = 'idp', 'ВПО (внутрішньо переміщена особа)'
        OTHER = 'other', 'Інше'

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='recipient_profile',
        verbose_name='Користувач',
    )
    situation_type = models.CharField(
        'Тип ситуації',
        max_length=20,
        choices=SituationType.choices,
        blank=True,
    )
    emergency_contact_name = models.CharField(
        'Контактна особа (ім\'я)',
        max_length=100,
        blank=True,
    )
    emergency_contact_phone = models.CharField(
        'Контактна особа (телефон)',
        max_length=20,
        blank=True,
    )

    class Meta:
        verbose_name = 'Профіль отримувача'
        verbose_name_plural = 'Профілі отримувачів'

    def __str__(self):
        return f"Профіль отримувача: {self.user.get_full_name()}"
