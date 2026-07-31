from django.test import TestCase

from panoview.models import PanoramaItem, Sequence


class PanoviewApiTest(TestCase):
    """
    Sequence / PanoramaItem are unmanaged models backed by tables populated
    externally (see import_panoramas.py at the project root), not by Django
    fixtures. As in roads/tests.py, tests read whatever pictures are already
    present in the shared database and skip picture-specific assertions when
    there is none.
    """

    @classmethod
    def setUpTestData(cls):
        cls.sequence = Sequence.objects.first()
        cls.item = PanoramaItem.objects.first()

    def test_catalog(self):
        """
        /panoview/catalog.json returns a STAC Catalog
        """
        response = self.client.get("/panoview/catalog.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "Catalog")
        self.assertIn("links", data)

    def test_collections_list(self):
        """
        /panoview/collections lists every imported sequence
        """
        response = self.client.get("/panoview/collections")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data["collections"], list)
        if self.sequence:
            ids = [c["id"] for c in data["collections"]]
            self.assertIn(self.sequence.id, ids)

    def test_collection_detail(self):
        """
        /panoview/collections/<seq_id>/collection.json returns that sequence
        """
        if not self.sequence:
            self.skipTest("No Sequence found in database")
        url = f"/panoview/collections/{self.sequence.id}/collection.json"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "Collection")
        self.assertEqual(data["id"], self.sequence.id)

    def test_collection_detail_unknown(self):
        """
        Unknown sequence id returns a 404
        """
        response = self.client.get("/panoview/collections/does-not-exist/collection.json")
        self.assertEqual(response.status_code, 404)

    def test_item_detail(self):
        """
        /panoview/collections/<seq_id>/items/<item_id> returns that picture
        """
        if not self.item:
            self.skipTest("No PanoramaItem found in database")
        url = f"/panoview/collections/{self.item.sequence_id}/items/{self.item.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "Feature")
        self.assertEqual(data["id"], self.item.id)
        self.assertEqual(data["collection"], self.item.sequence_id)
        self.assertEqual(data["geometry"]["type"], "Point")
        self.assertIn("image", data["assets"])

    def test_item_detail_unknown(self):
        """
        Unknown item id returns a 404
        """
        if not self.sequence:
            self.skipTest("No Sequence found in database")
        url = f"/panoview/collections/{self.sequence.id}/items/does-not-exist"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_search(self):
        """
        /panoview/search?ids=... returns a FeatureCollection containing that picture
        """
        if not self.item:
            self.skipTest("No PanoramaItem found in database")
        response = self.client.get(f"/panoview/search?ids={self.item.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "FeatureCollection")
        ids = [feature["id"] for feature in data["features"]]
        self.assertIn(self.item.id, ids)

    def test_panorama_view(self):
        """
        /panoview/<item_id> serves the HTML viewer for that picture
        """
        if not self.item:
            self.skipTest("No PanoramaItem found in database")
        response = self.client.get(f"/panoview/{self.item.id}")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.item.id, content)
        self.assertIn(self.item.sequence_id, content)

    def test_panorama_view_unknown(self):
        """
        Unknown picture id returns a 404
        """
        response = self.client.get("/panoview/does-not-exist")
        self.assertEqual(response.status_code, 404)
