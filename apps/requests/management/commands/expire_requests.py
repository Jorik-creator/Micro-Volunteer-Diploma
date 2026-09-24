"""
Management command: expire_requests

Marks overdue help requests as expired and notifies everyone involved.
Normally this runs as part of `run_periodic_tasks` / POST /tasks/run/.

Usage:
    python manage.py expire_requests [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.requests.models import HelpRequest
from apps.requests.services import expire_overdue


class Command(BaseCommand):
    help = "Marks active requests whose needed_date has passed as expired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many active requests are overdue without changing them.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            count = HelpRequest.objects.filter(
                status=HelpRequest.Status.ACTIVE, needed_date__lt=timezone.now()
            ).count()
            self.stdout.write(self.style.WARNING(f"[dry-run] Would expire {count} request(s)."))
            return

        expired = expire_overdue()
        if expired == 0:
            self.stdout.write(self.style.SUCCESS("No requests to expire."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully expired {expired} request(s)."))
