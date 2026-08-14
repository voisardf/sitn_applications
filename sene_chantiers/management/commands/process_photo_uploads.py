"""Worker loop: sanitise queued photos and fire the deadline digest.

Runs in its own container, the only one with /data mounted read-write.
The Photo.status column is the queue; no message broker is involved.
"""

import time

from django.core.management import call_command, get_commands
from django.core.management.base import BaseCommand
from django.utils import timezone

from sene_chantiers.services import photos

POLL_SECONDS = 10


class Command(BaseCommand):
    help = "Sanitise uploaded photos and move them to the read-only data volume."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop", action="store_true",
            help="Keep polling instead of processing one batch and exiting.",
        )
        parser.add_argument(
            "--interval", type=int, default=POLL_SECONDS,
            help="Seconds between polls when looping.",
        )

    def handle(self, *args, **options):
        if not options["loop"]:
            self._process_once()
            return

        # Second periodic job, so the deployment needs one worker, not two.
        last_digest_hour = None
        while True:
            self._process_once()
            last_digest_hour = self._maybe_send_digest(last_digest_hour)
            time.sleep(options["interval"])

    def _process_once(self):
        processed, failed = photos.process_pending()
        if processed or failed:
            self.stdout.write(
                f"photos: {processed} traitée(s), {failed} rejetée(s)"
            )

    def _maybe_send_digest(self, last_digest_hour):
        """Run the weekly digest once when its configured slot comes round."""
        from django.conf import settings

        now = timezone.localtime()
        slot = (now.year, now.timetuple().tm_yday, now.hour)
        if last_digest_hour == slot:
            return last_digest_hour
        if now.weekday() != settings.SENE_CHANTIERS_DEADLINE_DIGEST_DAY_OF_WEEK:
            return last_digest_hour
        if now.hour != settings.SENE_CHANTIERS_DEADLINE_DIGEST_HOUR:
            return last_digest_hour

        # The digest command lands with the notifications step; until then
        # the photo loop runs on its own rather than failing every Monday.
        if "send_deadline_digest" not in get_commands():
            return slot

        call_command("send_deadline_digest")
        return slot
