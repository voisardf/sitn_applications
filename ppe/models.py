import os

from django.core.validators import FileExtensionValidator
from django.contrib.gis.db import models
from django.utils.timezone import now
from django.conf import settings


def unique_folder_path(instance, filename):
    """ Define the new storage path from login_code
        and prefix the uploaded files with the date
    """
    date_prefix = now().strftime('%Y%m%d_%H%M%S')
    new_filename = f"{date_prefix}.zip"
    return '/'.join(["ppe", f"{instance.dossier_ppe.id}", new_filename])

def rename_pdf_accord(instance, filename):
    """ Define the new filename using a date prefix
    """
    date_prefix = now().strftime('%Y%m%d_%H%M%S')
    new_filename = f"{date_prefix}_{filename}"
    return '/'.join(['ppe', 'confirmations', new_filename])

class Geolocalisation(models.Model):
    geom = models.PointField(srid=settings.DEFAULT_SRID)

    class Meta:
        db_table = 'ppe\".\"geolocalisation'


class AdresseFacturation(models.Model):
    type_personne = models.CharField(
        choices=(
            ("pp", "Personne physique"),
            ("pm", "Personne morale")
              ),
                max_length=50, default="pp")
    nom_raison_sociale = models.CharField(max_length=150)
    prenom = models.CharField(max_length=100)
    complement = models.CharField(max_length=100, blank=True)
    rue = models.CharField(max_length=100)
    no_rue = models.CharField(max_length=10, blank=True)
    npa = models.IntegerField()
    localite = models.CharField(max_length=100)
    file = models.FileField(upload_to=rename_pdf_accord, validators=[
        FileExtensionValidator(["pdf"])
    ])

    def __str__(self):
        return self.nom_raison_sociale

    def filename(self):
        return os.path.basename(self.file.name)

    class Meta:
        ordering = ["nom_raison_sociale"]
        db_table = 'ppe\".\"adresse_facturation'
        verbose_name = "Adresse facturation"
        verbose_name_plural = "Adresses facturation"


class ContactPrincipal(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    no_tel = models.CharField(max_length=15)
    raison_sociale = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return self.nom + str(' ') + self.prenom

    class Meta:
        ordering = ["nom"]
        db_table = 'ppe\".\"contact_principal'
        verbose_name = "Contact principal"
        verbose_name_plural = "Contacts principaux"


class Notaire(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    complement = models.CharField(max_length=100, blank=True)
    rue = models.CharField(max_length=100)
    no_rue = models.CharField(max_length=10, blank=True)
    npa = models.IntegerField()
    localite = models.CharField(max_length=100)

    def __str__(self):
        return self.nom + str(' ') + self.prenom

    class Meta:
        ordering = ["nom"]
        db_table = 'ppe\".\"notaire'
        verbose_name = "Notaire"
        verbose_name_plural = "Notaires"


class Signataire(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    complement = models.CharField(max_length=100, blank=True)
    rue = models.CharField(max_length=100)
    no_rue = models.CharField(max_length=10, blank=True)
    npa = models.IntegerField()
    localite = models.CharField(max_length=100)

    def __str__(self):
        return self.nom + str(' ') + self.prenom

    class Meta:
        ordering = ["nom"]
        db_table = 'ppe\".\"signataire'
        verbose_name = "Signataire"
        verbose_name_plural = "Signataires"


class DossierPPE(models.Model):
    class DossierStatut(models.TextChoices):
        A = "A", "Abandonné"
        C = "C", "En correction"
        E = "E", "Envoyé"
        P = "P", "En préparation"
        T = "T", "En traitement"
        V = "V", "Validé"

    class TypeDossier(models.TextChoices):
        C = "C", "Constitution"
        R = "R", "Révision"
        M = "M", "Modification"
        I = "I", "Indéfini"
             
    login_code = models.CharField(max_length=16)
    cadastre = models.CharField(max_length=50)
    numcad = models.IntegerField()
    nummai = models.CharField(max_length=10)
    coord_E = models.IntegerField()
    coord_N = models.IntegerField()
    statut = models.CharField(
        max_length=20,
        choices=DossierStatut.choices,
        default=DossierStatut.P)
    type_dossier = models.CharField(
        max_length=20,
        choices=TypeDossier.choices,
        default=TypeDossier.I)
    revision_jouissances = models.CharField(max_length=3, default=None, blank=True, null=True)
    elements_rf_identiques = models.CharField(max_length=3, default=None, blank=True, null=True)
    nouveaux_droits = models.CharField(max_length=3, default=None, blank=True, null=True)
    ref_geoshop = models.CharField(max_length=20, default=None, blank=True, null=True)
    ref_dossier_initial = models.IntegerField(blank=True, null=True)
    contact_principal = models.ForeignKey(ContactPrincipal, on_delete=models.CASCADE)
    signataire = models.ForeignKey(Signataire, on_delete=models.CASCADE)
    notaire = models.ForeignKey(Notaire, on_delete=models.CASCADE)
    adresse_facturation = models.ForeignKey(AdresseFacturation, on_delete=models.CASCADE)
    aff_infolica = models.IntegerField(default=0,null=True)
    date_creation = models.DateTimeField("Date de création", auto_now=True)
    date_soumission = models.DateTimeField("Date de soumission", auto_now=True, blank=True)
    date_validation = models.DateTimeField("Date de validation", auto_now=True, blank=True)
    geom = models.PointField(srid=settings.DEFAULT_SRID)
    
    class Meta:
        db_table = 'ppe\".\"dossier_ppe'
        verbose_name = "Dossier PPE"
        verbose_name_plural = "Dossiers PPE"

class Zipfile(models.Model):
    class FileStatut(models.TextChoices):
        CAA = "CAA", "Contrôle automatique : archivé"
        CAC = "CAC", "Contrôle automatique : en cours"
        CAE = "CAE", "Contrôle automatique : erreurs à corriger"
        ERR = "ERR", "Contrôle automatique : erreur interne"
        CAV = "CAV", "Contrôle automatique : validé"
        CMS = "CMS", "Contrôle manuel : en cours (CMS)"
        CMC = "CMC", "Contrôle manuel : en cours"
        CME = "CME", "Contrôle manuel : erreurs à corriger"
        CMV = "CMV", "Contrôle manuel : validé"
        DPV = "DPV", "Dossier papier validé"

    zipfile = models.FileField(upload_to=unique_folder_path, validators=[
        FileExtensionValidator(["zip"])
    ])
    upload_date = models.DateTimeField("Date de chargement", auto_now=True)
    file_statut = models.CharField(
        max_length=3,
        choices=FileStatut.choices,
        default=FileStatut.CAC,
    )
    dossier_ppe = models.ForeignKey(DossierPPE, on_delete=models.CASCADE, related_name="zipfiles", blank=True)

    class Meta:
        ordering = ["-upload_date"]
        db_table = 'ppe\".\"zipfile'

    def filename(self):
        return os.path.basename(self.zipfile.name)


class GeoshopCadastreOrder(models.Model):
    date_ordered = models.DateTimeField()
    date_processed = models.DateTimeField()
    geom = models.PolygonField(srid=settings.DEFAULT_SRID)

    class Meta:
        managed = False
        db_table = 'ppe_static\".\"geoshop_order'
