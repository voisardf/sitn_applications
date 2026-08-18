"""Photos : validation au dépôt et sanitisation par le worker."""

import io

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from ..models import Photo, PhotoStatus
from ..services import photos
from .factories import (
    jpeg_bytes,
    make_chantier,
    make_control_report,
    make_user,
)


class MemberClientMixin:
    def setUp(self):
        super().setUp()
        self.user = make_user("membre")
        self.client = Client()
        self.client.force_login(self.user)


class PhotoUploadTest(MemberClientMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999500)
        self.report = make_control_report(chantier=self.chantier)
        self.url = reverse(
            "sene_chantiers:photo_upload", args=["controle", self.report.pk]
        )

    def test_valid_upload_is_queued(self):
        response = self.client.post(
            self.url,
            {"photo": SimpleUploadedFile("site.jpg", jpeg_bytes(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 201)
        photo = self.report.photos.get()
        self.assertEqual(photo.status, PhotoStatus.PENDING)
        self.assertTrue(photo.raw_upload)
        self.assertFalse(photo.image)

    def test_forbidden_extension_is_refused(self):
        response = self.client.post(
            self.url,
            {
                "photo": SimpleUploadedFile(
                    "payload.svg", b"<svg onload=alert(1)>", "image/svg+xml"
                )
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.report.photos.count(), 0)

    @override_settings(SENE_CHANTIERS_PHOTO_MAX_SIZE_MB=1)
    def test_oversize_upload_is_refused(self):
        oversized = b"\xff\xd8\xff" + b"0" * (1024 * 1024 + 1024)
        response = self.client.post(
            self.url,
            {"photo": SimpleUploadedFile("huge.jpg", oversized, "image/jpeg")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("volumineux", response.json()["error"])

    def test_locked_report_refuses_uploads(self):
        self.report.is_locked = True
        self.report.save(update_fields=["is_locked"])
        response = self.client.post(
            self.url,
            {"photo": SimpleUploadedFile("site.jpg", jpeg_bytes(), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 403)


class PhotoSanitizeTest(TestCase):
    """Le ré-encodage doit produire une image sans métadonnée."""

    def setUp(self):
        self.report = make_control_report(chantier=make_chantier(satac_number=999510))

    def _queue(self, payload, name="photo.jpg"):
        photo = Photo(control_report=self.report, status=PhotoStatus.PENDING)
        photo.raw_upload.save(name, ContentFile(payload), save=True)
        return photo

    def test_valid_photo_is_moved_and_the_staging_copy_cleared(self):
        photo = self._queue(jpeg_bytes())
        self.assertTrue(photos.sanitize(photo))
        photo.refresh_from_db()
        self.assertEqual(photo.status, PhotoStatus.DONE)
        self.assertTrue(photo.image)
        self.assertFalse(photo.raw_upload)

    def test_disguised_non_image_is_rejected(self):
        photo = self._queue(b"<script>alert(1)</script>" * 40)
        self.assertFalse(photos.sanitize(photo))
        photo.refresh_from_db()
        self.assertEqual(photo.status, PhotoStatus.FAILED)
        self.assertFalse(photo.image)
        self.assertIn("volumineux", photo.error_message)

    def test_jpeg_comment_payload_does_not_survive(self):
        payload = jpeg_bytes(comment=b"<script>alert(document.cookie)</script>")
        self.assertIn(b"<script>", payload)
        photo = self._queue(payload)
        photos.sanitize(photo)
        photo.refresh_from_db()
        photo.image.open("rb")
        cleaned = photo.image.read()
        photo.image.close()
        self.assertNotIn(b"<script>", cleaned)

    def test_exif_payload_does_not_survive(self):
        buffer = io.BytesIO()
        image = Image.new("RGB", (200, 150), (30, 90, 160))
        exif = image.getexif()
        exif[0x9286] = "<script>steal()</script>"
        image.save(buffer, "JPEG", exif=exif.tobytes())
        payload = buffer.getvalue()
        self.assertIn(b"script", payload)

        photo = self._queue(payload)
        photos.sanitize(photo)
        photo.refresh_from_db()
        photo.image.open("rb")
        cleaned = photo.image.read()
        photo.image.close()
        self.assertNotIn(b"script", cleaned)


class PhotoUrlPrefixTest(MemberClientMixin, TestCase):
    """Les URL du bloc photo doivent survivre au préfixe de script.

    Les instances déployées tournent sous ROOTURL (« /apps_inter »), que
    Django applique comme FORCE_SCRIPT_NAME. Un chemin écrit à la main
    dans le JavaScript ignore ce préfixe : le téléversement échoue en 404
    sur les serveurs et fonctionne parfaitement en local, ce qui rend la
    panne difficile à attribuer.
    """

    def setUp(self):
        super().setUp()
        self.chantier = make_chantier(satac_number=999610)
        self.report = make_control_report(chantier=self.chantier)

    def _block(self):
        response = self.client.get(
            reverse("sene_chantiers:control_report_edit", args=[999610])
        )
        return response.content.decode()

    def test_endpoints_are_rendered_by_django_not_the_script(self):
        html = self._block()
        for attr in ("data-url-upload", "data-url-status",
                     "data-url-caption", "data-url-remove"):
            self.assertIn(attr, html)

    def test_script_builds_no_application_path_itself(self):
        source = (
            settings.BASE_DIR / "sene_chantiers/static/sene_chantiers/photos.js"
        ).read_text(encoding="utf-8")
        # Un seul chemin codé en dur suffit à casser les instances déployées.
        self.assertNotIn("/sene_chantiers/", source)

    def test_endpoints_match_django_url_resolution(self):
        """Chaque URL du bloc est celle que Django résout.

        C'est la garantie qui compte : puisqu'elles viennent de
        `{% url %}`, elles portent le préfixe de script quel qu'il soit.
        Vérifier le préfixe lui-même reviendrait à tester Django.
        """
        html = self._block()
        expected = {
            "data-url-upload": reverse(
                "sene_chantiers:photo_upload",
                kwargs={"kind": "controle", "pk": self.report.pk}),
            "data-url-status": reverse(
                "sene_chantiers:photo_status",
                kwargs={"kind": "controle", "pk": self.report.pk}),
            "data-url-caption": reverse(
                "sene_chantiers:photo_caption", kwargs={"pk": 0}),
            "data-url-remove": reverse(
                "sene_chantiers:photo_delete", kwargs={"pk": 0}),
        }
        for attr, url in expected.items():
            self.assertIn(f'{attr}="{url}"', html)
