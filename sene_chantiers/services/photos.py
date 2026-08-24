"""Photo sanitisation.

Uploads land in /upload (writable by the web container) and are processed
out of band by the worker container, which is the only service with /data
mounted read-write. Sanitising means validating the type and re-encoding
through Pillow, which drops anything embedded that is not image data.
"""

import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from ..models import Photo, PhotoStatus

logger = logging.getLogger(__name__)

# Re-encoding target. JPEG for photographs, PNG kept for anything with
# transparency so screenshots of plans do not gain a black background.
JPEG_QUALITY = 85
MAX_PIXELS = 4000  # longest edge; report photos never need more


def sanitize(photo):
    """Validate and re-encode one photo, then move it to /data.

    Returns True on success. Failures are recorded on the row itself so
    the inspector sees why, rather than the file vanishing silently.
    """
    photo.status = PhotoStatus.PROCESSING
    photo.save(update_fields=["status"])

    try:
        photo.raw_upload.open("rb")
        payload = photo.raw_upload.read()
        photo.raw_upload.close()

        with Image.open(BytesIO(payload)) as image:
            image.verify()  # rejects truncated or non-image payloads

        # verify() leaves the file unusable, so reopen for the re-encode.
        with Image.open(BytesIO(payload)) as image:
            image = _normalise(image)
            has_alpha = image.mode in ("RGBA", "LA", "P")
            image = image.convert("RGBA" if has_alpha else "RGB")
            image = _strip_metadata(image)

            buffer = BytesIO()
            if has_alpha:
                image.save(buffer, format="PNG", optimize=True)
                extension = "png"
            else:
                image.save(
                    buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True
                )
                extension = "jpg"

        base = os.path.splitext(os.path.basename(photo.raw_upload.name))[0]
        photo.image.save(f"{base}.{extension}", ContentFile(buffer.getvalue()),
                         save=False)
        photo.status = PhotoStatus.DONE
        photo.error_message = ""
        photo.processed_at = timezone.now()
        photo.save(update_fields=["image", "status", "error_message",
                                  "processed_at"])
        _discard_raw(photo)
        return True

    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning("Photo %s rejected: %s", photo.pk, exc)
        photo.status = PhotoStatus.FAILED
        photo.error_message = (
            "Le fichier image semble être trop volumineux ou contient une erreur."
        )
        photo.processed_at = timezone.now()
        photo.save(update_fields=["status", "error_message", "processed_at"])
        _discard_raw(photo)
        return False


def _normalise(image):
    """Apply the EXIF rotation and cap the resolution."""
    try:
        from PIL import ImageOps

        image = ImageOps.exif_transpose(image)
    except Exception:  # pragma: no cover - EXIF is best-effort
        pass
    if max(image.size) > MAX_PIXELS:
        image.thumbnail((MAX_PIXELS, MAX_PIXELS))
    return image


def _strip_metadata(image):
    """Return an image holding pixel data and nothing else.

    Converting alone is not enough: Pillow carries EXIF blocks and JPEG
    comments through `image.info` into the re-encoded file, so anything
    hidden there would survive. Rebuilding from the raw pixel bytes gives
    a fresh image with empty metadata.
    """
    return Image.frombytes(image.mode, image.size, image.tobytes())


def _discard_raw(photo):
    """The staging copy is removed whether processing succeeded or not."""
    if not photo.raw_upload:
        return
    try:
        photo.raw_upload.delete(save=False)
    except OSError:
        logger.warning("Could not remove staged upload for photo %s", photo.pk)
    photo.raw_upload = ""
    photo.save(update_fields=["raw_upload"])


def process_pending(limit=50):
    """Sanitise queued photos. Returns (processed, failed)."""
    processed = failed = 0
    queryset = Photo.objects.filter(status=PhotoStatus.PENDING)[:limit]
    for photo in queryset:
        if sanitize(photo):
            processed += 1
        else:
            failed += 1
    return processed, failed
