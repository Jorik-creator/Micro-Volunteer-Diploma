from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("mark-read/<int:pk>/", views.mark_read, name="mark-read"),
    path("mark-all-read/", views.mark_all_read, name="mark-all-read"),
]
