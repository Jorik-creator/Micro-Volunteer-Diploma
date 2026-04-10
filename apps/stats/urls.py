from django.urls import path

from . import views

app_name = "stats"

urlpatterns = [
    path("dashboard/", views.StatsView.as_view(), name="dashboard"),
    path("data/", views.stats_data, name="stats-data"),
]
