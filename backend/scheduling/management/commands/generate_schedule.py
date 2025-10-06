from __future__ import annotations

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from scheduling.domain.repositories import ServiceRepository
from scheduling.services.calendar import ensure_month_services
from scheduling.services.suggestion import suggest_for_month

class Command(BaseCommand):
    help = "Generate schedule suggestions for a given month (ensures services first)."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, help="Target year (defaults: current or --next).")
        parser.add_argument("--month", type=int, help="Target month [1..12] (defaults: current or --next).")
        parser.add_argument(
            "--next",
            action="store_true",
            help="Use next month relative to local time (overrides year/month if omitted).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Persist suggestions (otherwise only ensures services).",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="Username to attribute as generator of suggestions (optional).",
        )

    def handle(self, *args, **opts):
        today = timezone.localdate()
        year = opts["year"]
        month = opts["month"]
        use_next = bool(opts["next"])

        if use_next and (year is None or month is None):
            year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        elif year is None or month is None:
            year, month = today.year, today.month

        created_services = ensure_month_services(year, month)
        svc_count = ServiceRepository.month_services(year, month).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"[ensure] {created_services} service(s) created; total in {year}-{month:02d}: {svc_count}"
            )
        )

        if not opts.get("commit"):
            self.stdout.write(
                f"Dry-run completed for {year}-{month:02d}. Use --commit to create suggestions."
            )
            return

        user = None
        username = opts.get("user")
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User '{username}' not found. Continuing without user attribution."))
        created_flag, count = suggest_for_month(year, month, user=user)
        created_msg = "created" if created_flag else "existing"
        self.stdout.write(
            self.style.SUCCESS(f"[suggest] Schedule {created_msg}; {count} suggestion(s) added for {year}-{month:02d}.")
        )
