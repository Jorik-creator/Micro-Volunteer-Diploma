"""
Context processors для застосунку notifications.

Надає шаблонам глобальну змінну з кількістю непрочитаних сповіщень:
  unread_notifications  — повертає {'unread_count': int} для кожного запиту
"""

from .models import Notification


# ---------------------------------------------------------------------------
# Кількість непрочитаних сповіщень
# ---------------------------------------------------------------------------


def unread_notifications(request):
    """
    Повертає кількість непрочитаних сповіщень для авторизованого користувача.

    Для анонімних користувачів завжди повертає 0 — виняток ніколи не виникає.
    Використовує лише Django ORM без сирого SQL.

    Повертає:
        dict: {'unread_count': int} — кількість непрочитаних сповіщень
    """
    if request.user.is_authenticated:
        # Рахуємо лише непрочитані сповіщення поточного користувача
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {"unread_count": count}

    # Анонімний користувач — повертаємо 0 без звернення до БД
    return {"unread_count": 0}
