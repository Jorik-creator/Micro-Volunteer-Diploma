from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Review(models.Model):
    """Відгук після виконання запиту допомоги."""

    author = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='reviews_written',
        verbose_name='Автор',
    )
    target = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='reviews_received',
        verbose_name='Про кого',
    )
    help_request = models.ForeignKey(
        'requests.HelpRequest',
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='Запит допомоги',
    )
    rating = models.IntegerField(
        'Оцінка',
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField('Коментар')
    created_at = models.DateTimeField('Дата створення', auto_now_add=True)

    class Meta:
        verbose_name = 'Відгук'
        verbose_name_plural = 'Відгуки'
        ordering = ['-created_at']
        unique_together = ['author', 'help_request']

    def __str__(self):
        return f"{self.author} → {self.target}: {self.rating}/5"
