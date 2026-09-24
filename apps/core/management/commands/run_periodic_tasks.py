from django.core.management.base import BaseCommand

from apps.core.tasks import run_periodic_tasks


class Command(BaseCommand):
    help = "Run all periodic jobs once (expiry, auto-confirmation, reminders)."

    def handle(self, *args, **options):
        for name, result in run_periodic_tasks().items():
            self.stdout.write(f"{name}: {result}")
