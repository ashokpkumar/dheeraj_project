"""
Management command to display system configuration and startup information.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from automation.config import is_orchestrator_mode, get_celery_config, get_redis_url


class Command(BaseCommand):
    help = 'Display system configuration and startup information'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed configuration',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS("AUTOMATION APP CONFIGURATION"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        # Mode
        mode = 'ORCHESTRATOR' if is_orchestrator_mode() else 'WORKER'
        mode_color = self.style.SUCCESS if is_orchestrator_mode() else self.style.WARNING
        self.stdout.write(f"Mode: {mode_color(mode)}")

        # Celery
        self.stdout.write(f"\nCelery Configuration:")
        self.stdout.write(f"  Broker URL: {get_redis_url()}")
        self.stdout.write(f"  Result Backend: {settings.CELERY_RESULT_BACKEND}")
        self.stdout.write(f"  Orchestrator Mode: {is_orchestrator_mode()}")

        # Database
        self.stdout.write(f"\nDatabase Configuration:")
        self.stdout.write(f"  Engine: {settings.DATABASES['default']['ENGINE']}")
        self.stdout.write(f"  Name: {settings.DATABASES['default']['NAME']}")
        self.stdout.write(f"  Host: {settings.DATABASES['default']['HOST']}")

        # Services
        self.stdout.write(f"\nServices:")
        self.stdout.write(f"  Django Web: :8000")
        self.stdout.write(f"  Flower UI: :5555")
        self.stdout.write(f"  Redis: :6379")

        if is_orchestrator_mode():
            self.stdout.write(self.style.WARNING("\n⚠️  SCHEDULER ENABLED"))
            self.stdout.write("   This instance will manage scheduled jobs")
        else:
            self.stdout.write(self.style.WARNING("\n⚠️  SCHEDULER DISABLED"))
            self.stdout.write("   This instance will only execute tasks")

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70 + "\n"))

        if options['verbose']:
            self.stdout.write("\nDetailed Settings:")
            self.stdout.write(f"  DEBUG: {settings.DEBUG}")
            self.stdout.write(f"  ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")
            self.stdout.write(f"  TIME_ZONE: {settings.TIME_ZONE}")
            self.stdout.write(f"  INSTALLED_APPS: {', '.join(settings.INSTALLED_APPS[:3])}...")
