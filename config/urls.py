"""
URL configuration for MicroVolunteer project.

App URL includes are added as each app is developed.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.accounts.views import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("requests/", include("apps.requests.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("stats/", include("apps.stats.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
