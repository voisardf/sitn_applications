"""Weekly digest of corrective measures approaching or past deadline.

Fired by the worker loop at the configured day and hour, and runnable by
hand for testing.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from sene_chantiers.services import deadlines


class Command(BaseCommand):
    help = "Email each inspector the corrective measures they still owe."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be sent without sending anything.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        grouped = deadlines.by_inspector(today)

        if not grouped:
            self.stdout.write("Aucune mesure à échéance : aucun envoi.")
            return

        for inspector, rows in grouped.items():
            overdue = sum(1 for r in rows if r["urgency"] == deadlines.OVERDUE)
            target = inspector.email or "(pas d'adresse)"
            self.stdout.write(
                f"{target}: {len(rows)} mesure(s), dont {overdue} en retard"
            )

        sent = deadlines.send_digest(today, dry_run=options["dry_run"])
        verb = "auraient été envoyés" if options["dry_run"] else "envoyés"
        self.stdout.write(self.style.SUCCESS(f"{sent} digest(s) {verb}."))
