"""
Views для застосунку notifications.

Список сповіщень:
  NotificationListView  — пагінований список сповіщень поточного користувача

Дії зі сповіщеннями:
  mark_read      — позначити одне сповіщення як прочитане (POST)
  mark_all_read  — позначити всі непрочитані сповіщення як прочитані (POST)
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView

from .models import Notification


# ---------------------------------------------------------------------------
# Список сповіщень
# ---------------------------------------------------------------------------


class NotificationListView(LoginRequiredMixin, ListView):
    """Пагінований список сповіщень поточного користувача."""

    model = Notification
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        # Повертаємо лише сповіщення авторизованого користувача
        return Notification.objects.filter(user=self.request.user)


# ---------------------------------------------------------------------------
# Позначити одне сповіщення як прочитане
# ---------------------------------------------------------------------------


@login_required
def mark_read(request, pk):
    """
    Позначає одне сповіщення як прочитане.
    Дозволено лише POST-запити; власник сповіщення перевіряється через get_object_or_404.
    """
    if request.method != "POST":
        # GET та інші методи не дозволені
        return HttpResponseNotAllowed(["POST"])

    # Отримуємо сповіщення, що належить поточному користувачу
    notification = get_object_or_404(Notification, pk=pk, user=request.user)

    # Оновлюємо лише поле is_read для ефективності
    notification.is_read = True
    notification.save(update_fields=["is_read"])

    messages.success(request, "Сповіщення позначено як прочитане")
    return redirect("notifications:notification-list")


# ---------------------------------------------------------------------------
# Позначити всі сповіщення як прочитані
# ---------------------------------------------------------------------------


@login_required
def mark_all_read(request):
    """
    Позначає всі непрочитані сповіщення поточного користувача як прочитані.
    Дозволено лише POST-запити; використовує bulk update для ефективності.
    """
    if request.method != "POST":
        # GET та інші методи не дозволені
        return HttpResponseNotAllowed(["POST"])

    # Масове оновлення — один SQL UPDATE замість N окремих запитів
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    messages.success(request, "Всі сповіщення позначено як прочитані")
    return redirect("notifications:notification-list")
