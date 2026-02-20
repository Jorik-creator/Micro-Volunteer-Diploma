from django.db import models


class Notification(models.Model):
    """Внутрішнє сповіщення для користувача."""

    class Type(models.TextChoices):
        NEW_RESPONSE = 'new_response', 'Новий відгук на запит'
        REQUEST_ACCEPTED = 'request_accepted', 'Запит прийнято'
        REQUEST_REJECTED = 'request_rejected', 'Запит відхилено'
        REQUEST_COMPLETED = 'request_completed', 'Запит виконано'
        NEW_REVIEW = 'new_review', 'Новий відгук про вас'
        NEW_NEARBY_REQUEST = 'new_nearby_request', 'Новий запит поблизу'

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Користувач',
    )
    type = models.CharField('Тип', max_length=25, choices=Type.choices)
    title = models.CharField('Заголовок', max_length=200)
    message = models.TextField('Текст')
    related_request = models.ForeignKey(
        'requests.HelpRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name='Пов\'язаний запит',
    )
    is_read = models.BooleanField('Прочитано', default=False)
    created_at = models.DateTimeField('Дата створення', auto_now_add=True)

    class Meta:
        verbose_name = 'Сповіщення'
        verbose_name_plural = 'Сповіщення'
        ordering = ['-created_at']

    def __str__(self):
        status = '✓' if self.is_read else '●'
        return f"{status} {self.title} → {self.user}"
