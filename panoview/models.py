from django.contrib.gis.db import models


class Sequence(models.Model):
    """
    A STAC Collection: one mobile-mapping capture run, identified as "{site}_{version}"
    (e.g. "RNE2_V01"), matching the gps-imu_<site>_<version>_*.txt source file it was
    imported from.
    """

    id = models.CharField(max_length=64, primary_key=True)
    site = models.CharField(max_length=32)
    version = models.CharField(max_length=32)
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    base_image_url = models.URLField(max_length=500)

    class Meta:
        ordering = ["id"]
        managed = False
        db_table = 'routes\".\"rt201_panoview_sequence'

    def __str__(self):
        return self.id


class PanoramaItem(models.Model):
    """
    A STAC Item: a single 360 panorama picture
    """

    id = models.CharField(max_length=128, primary_key=True)
    sequence = models.ForeignKey(Sequence, related_name="items", on_delete=models.CASCADE)
    # Rank of the picture within its sequence, in original gps-imu file order.
    # Drives ordering and the STAC prev/next links.
    rank = models.PositiveIntegerField()
    geom = models.PointField(srid=2056, dim=3)
    captured_at = models.DateTimeField()
    # view:azimuth / pers:pitch / pers:roll STAC properties, in degrees.
    azimuth = models.FloatField()
    pitch = models.FloatField()
    roll = models.FloatField()
    image_name = models.CharField(max_length=255)
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["sequence_id", "rank"]
        constraints = [
            models.UniqueConstraint(fields=["sequence", "rank"], name="panoview_item_unique_sequence_rank"),
        ]
        db_table = 'routes\".\"rt202_panoview_item'
        managed = False

    def __str__(self):
        return self.id
