from django.conf import settings
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _


class SearchSatac(models.Model):
    """FTS sur no. SATAC"""

    idobj = models.CharField(max_length=40, primary_key=True)
    instance_id = models.BigIntegerField()  # no. SATAC
    search_satac = models.CharField(max_length=30)  # label
    geom = models.PointField(srid=settings.DEFAULT_SRID)

    class Meta:
        managed = False
        db_table = 'searchtables"."search_satac'
        verbose_name = _("Recherche SATAC")

    def __str__(self):
        return self.search_satac


class At034AutorisationConstruire(models.Model):
    """Permis de construire"""

    idobj = models.CharField(max_length=40, primary_key=True)
    instance_id = models.BigIntegerField()  # no. SATAC
    debut_enquete = models.DateField(null=True)
    fin_enquete = models.DateField(null=True)
    cadastre = models.CharField(max_length=200, null=True)
    commune = models.CharField(max_length=100, null=True)
    idcom = models.SmallIntegerField(null=True)  # numcom
    categorie_ouvrage = models.CharField(max_length=200, null=True)
    type_construction = models.CharField(max_length=200, null=True)
    etat_dossier = models.CharField(max_length=200, null=True)
    parcelle = models.TextField(null=True)
    requerant = models.TextField(null=True)
    description_ouvrage = models.TextField(null=True)
    geom = models.PointField(srid=settings.DEFAULT_SRID)

    class Meta:
        managed = False
        db_table = 'amenagement"."at034_autorisation_construire'
        verbose_name = _("Autorisation de construire")

    def __str__(self):
        return str(self.instance_id)

