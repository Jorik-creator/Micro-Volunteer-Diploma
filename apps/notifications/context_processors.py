"""
Context processors для застосунку notifications.

Надає шаблонам глобальну змінну з кількістю непрочитаних сповіщень:
  unread_notifications  — повертає {'unread_count': int} для кожного запиту
"""

from .models import Notification

# ---------------------------------------------------------------------------
# Кількість непрочитаних сповіщень
# ---------------------------------------------------------------------------


def navigation(request):
    """Flags the navigation needs on every page."""
    from apps.accounts.permissions import is_moderator
    from apps.conversations.services import unread_count

    user = request.user
    return {
        "is_moderator": is_moderator(user),
        "unread_conversations": unread_count(user) if user.is_authenticated else 0,
    }


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
