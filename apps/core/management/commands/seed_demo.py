from django.core.management.base import BaseCommand

from apps.core import demo


class Command(BaseCommand):
    help = "Fill the database with portfolio demo data (use --reset to wipe non-admin data first)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all non-superuser accounts and their data before seeding.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            demo.wipe()
        result = demo.seed()
        self.stdout.write(self.style.SUCCESS(f"Demo data ready: {result}"))
