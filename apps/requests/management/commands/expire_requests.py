"""
Management command: expire_requests

Marks overdue help requests as expired.

Usage:
    python manage.py expire_requests

Schedule (cron every 30 minutes):
    */30 * * * * cd /app && python manage.py expire_requests

Race condition safety:
    The ORM UPDATE filters by both status='active' AND needed_date < now().
    If a request transitions to 'in_progress' between the queryset evaluation
    and the UPDATE, the SQL WHERE clause excludes it automatically.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.requests.models import HelpRequest


class Command(BaseCommand):
    help = "Marks active requests whose needed_date has passed as expired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many requests would be expired without making changes.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        qs = HelpRequest.objects.filter(
            status=HelpRequest.Status.ACTIVE,
            needed_date__lt=now,
        )

        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(f"[dry-run] Would expire {count} request(s).")
            )
            return

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No requests to expire."))
            return

        updated = qs.update(status=HelpRequest.Status.EXPIRED)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully expired {updated} request(s).")
        )
