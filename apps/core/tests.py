import pytest
from django.utils import timezone

from apps.requests.models import HelpRequest
from conftest import HelpRequestFactory

pytestmark = pytest.mark.django_db

URL = "/tasks/run/"


def test_disabled_without_secret(client, settings):
    settings.CRON_SECRET = ""
    assert client.post(URL).status_code == 404


def test_wrong_secret_is_rejected(client, settings):
    settings.CRON_SECRET = "s3cret"
    assert client.post(URL, HTTP_AUTHORIZATION="Bearer nope").status_code == 401


def test_get_not_allowed(client, settings):
    settings.CRON_SECRET = "s3cret"
    assert client.get(URL, HTTP_AUTHORIZATION="Bearer s3cret").status_code == 405


def test_runs_all_jobs(client, settings):
    settings.CRON_SECRET = "s3cret"
    overdue = HelpRequestFactory(needed_date=timezone.now() - timezone.timedelta(hours=1))

    response = client.post(URL, HTTP_AUTHORIZATION="Bearer s3cret")

    assert response.status_code == 200
    assert response.json() == {"expire_overdue": 1, "auto_confirm": 0, "send_reminders": 0}
    overdue.refresh_from_db()
    assert overdue.status == HelpRequest.Status.EXPIRED


def test_failing_job_does_not_stop_others(monkeypatch, settings):
    from apps.core import tasks

    monkeypatch.setattr(tasks, "PERIODIC_TASKS", ["apps.core.tests.boom", "apps.core.tests.ok"])

    assert tasks.run_periodic_tasks() == {"boom": "error", "ok": 1}


def boom():
    raise RuntimeError("fail")


def ok():
    return 1
