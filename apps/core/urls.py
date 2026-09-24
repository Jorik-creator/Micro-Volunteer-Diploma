from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("run/", views.run_tasks, name="run-tasks"),
]
