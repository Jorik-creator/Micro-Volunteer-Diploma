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
    assert response.json() == {
        "expire_overdue": 1,
        "auto_confirm": 0,
        "send_reminders": 0,
        "publish_due": 0,
        "send_review_reminders": 0,
        "reset_daily": "off",
    }
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


class TestDemo:
    def test_seed_builds_a_complete_world(self, settings):
        from django.core.management import call_command

        from apps.accounts.models import User
        from apps.conversations.models import Message
        from apps.moderation.models import Report, VerificationRequest
        from apps.reviews.models import Review

        call_command("seed_demo", verbosity=0)

        assert User.objects.filter(is_demo=True).count() == 3
        assert not User.objects.filter(is_demo=True, is_staff=True).exists()
        statuses = set(HelpRequest.objects.values_list("status", flat=True))
        assert {
            "active",
            "in_progress",
            "awaiting_confirmation",
            "completed",
            "pending_moderation",
        } <= statuses
        assert Message.objects.exists()
        assert Review.objects.published().exists()
        assert VerificationRequest.objects.filter(status="pending").exists()
        assert Report.objects.exists()

    def test_demo_buttons_log_into_seeded_accounts(self, client, settings):
        from apps.core import demo

        settings.DEMO_MODE = True
        demo.seed()
        for role in ("volunteer", "recipient", "moderator"):
            client.post(f"/accounts/demo/{role}/")
            assert "_auth_user_id" in client.session
            client.logout()

    def test_pages_render_for_every_demo_role(self, client, settings):
        from apps.accounts.models import User
        from apps.core import demo

        demo.seed()
        pages = [
            "/",
            "/requests/",
            "/requests/map/",
            "/conversations/",
            "/accounts/profile/",
            "/notifications/",
        ]
        for user in User.objects.filter(is_demo=True):
            client.force_login(user)
            for url in pages + [
                f"/requests/{pk}/" for pk in HelpRequest.objects.values_list("pk", flat=True)
            ]:
                assert client.get(url).status_code in (200, 404), (user, url)
        client.force_login(User.objects.get(username="demo.moderator"))
        for tab in ("verification", "requests", "reports"):
            assert client.get(f"/moderation/?tab={tab}").status_code == 200

    def test_daily_reset_only_once_a_day(self, settings):
        from datetime import timedelta

        from apps.accounts.models import User
        from apps.core import demo

        settings.DEMO_MODE = False
        assert demo.reset_daily() == "off"
        settings.DEMO_MODE = True
        assert demo.reset_daily() == 1  # nothing seeded yet
        assert demo.reset_daily() == 0
        User.objects.filter(is_demo=True).update(date_joined=timezone.now() - timedelta(days=2))
        assert demo.reset_daily() == 1


class TestImages:
    def test_shrinks_and_strips_metadata(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from apps.core.images import shrink

        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # camera make, stands in for GPS tags
        buffer = BytesIO()
        Image.new("RGB", (3000, 2000), "red").save(buffer, "JPEG", exif=exif)
        upload = SimpleUploadedFile("home.jpeg", buffer.getvalue(), content_type="image/jpeg")

        result = shrink(upload, 1280)

        with Image.open(result) as image:
            assert max(image.size) == 1280
            assert not image.getexif()
        assert result.name == "home.jpg"
