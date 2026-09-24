from django.db import migrations, models


def backfill(apps, schema_editor):
    """Requests completed before completed_at existed: best guess is the last update."""
    HelpRequest = apps.get_model("requests", "HelpRequest")
    HelpRequest.objects.filter(status="completed", completed_at__isnull=True).update(
        completed_at=models.F("updated_at")
    )
    HelpRequest.objects.update(status_changed_at=models.F("updated_at"))


class Migration(migrations.Migration):
    dependencies = [("requests", "0002_request_lifecycle")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
