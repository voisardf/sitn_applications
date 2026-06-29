from datetime import timedelta
import uuid
import logging

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from sitn.mixins import GeoJSONModelMixin

logger = logging.getLogger(__name__)


class AbstractDoctors(models.Model):

    class Avalability(models.TextChoices):
        UNKNOWN = "Unknown", _("Unknown")
        AVAILABLE = "Available", _("Available")
        NOT_AVAILABLE = "Not available", _("Not available")
        AVAILABLE_WITH_CONDITIONS = "Available with conditions", _("Available with conditions")

    availability = models.TextField(_("availability"), choices=Avalability.choices, default=Avalability.UNKNOWN)
    availability_conditions = models.TextField(_("availability_conditions"), blank=True, null=True)
    has_parking = models.BooleanField(_("has_parking"), null=True)
    has_disabled_access = models.BooleanField(_("has_disabled_access"), null=True)
    has_lift = models.BooleanField(_("has_lift"), null=True)
    spoken_languages = ArrayField(models.TextField(), verbose_name=_("spoken_languages"))
    is_rsn_member = models.BooleanField(_("is_rsn_member"), null=True)
    public_phone = models.CharField(_("public_phone"), blank=True, null=True, max_length=30)
    public_first_name = models.CharField(_("public_first_name"), blank=True, null=True, max_length=30)
    appointment_link = models.CharField(_("appointment_link"), blank=True, null=True, max_length=2000)

    class Meta:
        abstract = True


class St21AvailableDoctorsWithGeom(AbstractDoctors, GeoJSONModelMixin):
    id_person_address = models.TextField(_("id_person_address"), primary_key=True)
    nom = models.TextField()
    prenoms = models.TextField()
    profession = models.TextField()
    specialites = models.TextField()
    compl_formation = models.TextField()
    address = models.TextField()
    nopostal = models.TextField()
    localite = models.TextField()

    PUBLIC_FIELDS = [
        'id_person_address',
        'nom',
        'prenoms',
        'profession',
        'specialites',
        'compl_formation',
        'public_phone',
        'public_first_name',
        'appointment_link',
        'address',
        'nopostal',
        'localite',
        'availability',
        'availability_conditions',
        'has_parking',
        'has_disabled_access',
        'has_lift',
        'spoken_languages',
        'is_rsn_member',
        'appointment_link',
        'geom',
    ]
    geom = models.PointField(srid=settings.DEFAULT_SRID)

    class Meta:
        db_table = 'sante\".\"st21_available_doctors_with_geom'
        verbose_name = _("St21AvailableDoctorsWithGeom")
        managed=False
    
    def __str__(self):
        return "%s %s (%s)" % (
            self.nom,
            self.prenoms,
            self.id_person_address
        )


class St20AvailableDoctors(AbstractDoctors):
    """Doctor availability infos, without geom"""
    doctor = models.OneToOneField(
        St21AvailableDoctorsWithGeom,
        db_column="id_person_address",
        on_delete=models.CASCADE,
        verbose_name=_("doctor_nemedreg"),
        primary_key=True
    )
    login_email = models.CharField(blank=True, max_length=255)
    edit_guid = models.UUIDField(blank=True, null=True)
    guid_requested_when = models.DateTimeField(blank=True, null=True)
    last_edit = models.DateTimeField(blank=True, null=True)

    def prepare_for_edit(self):
        self.edit_guid = uuid.uuid4()

    @property
    def has_been_requested_recently(self):
        now = timezone.now()
        ten_minutes_ago = now - timedelta(minutes=10)
        if self.guid_requested_when == None:
            return False
        if self.guid_requested_when < ten_minutes_ago:
            logger.info('10 minutes cooldown')
            return False
        return True

    @property
    def is_edit_guid_valid(self):
        if not bool(self.edit_guid):
            logger.info('Edit guid is empty or null')
            return False
        return True

    def clean(self):
        # If availability is Available with conditions, make sure there are conditions
        if self.availability == AbstractDoctors.Avalability.AVAILABLE_WITH_CONDITIONS:
            if self.availability_conditions is None or len(self.availability_conditions) < 1:
                raise ValidationError(
                    {"availability_conditions": _("Availability conditions must be provided")}
                )
        # Sets availability conditions to blank if availability is not Available with conditions
        else:
            self.availability_conditions = ""


    def __str__(self):
        return "%s %s (%s)" % (
            self.doctor.nom,
            self.doctor.prenoms,
            self.doctor.id_person_address
        )

    class Meta:
        db_table = 'sante\".\"st20_available_doctors'
        verbose_name = _("St20AvailableDoctors")
        managed=False


class St19Cabinets(models.Model):
    """
    Needed for the data in the view
    """
    class Meta:
        db_table = 'sante\".\"st19_cabinets'
        managed=False


class St22DoctorChangeSuggestion(models.Model):
    """
    A change suggestion made by an anonymous user
    """
    doctor = models.ForeignKey(
        St21AvailableDoctorsWithGeom,
        db_column="id_person_address",
        on_delete=models.CASCADE,
        verbose_name=_("doctor_nemedreg")
    )
    availability = models.TextField(
        _("availability"),
        choices=AbstractDoctors.Avalability.choices,
        default=AbstractDoctors.Avalability.UNKNOWN)
    comments = models.TextField(_("comments"), blank=True)
    requested_when = models.DateTimeField(_("requested_when"), default=timezone.now)
    requestor = models.EmailField(_("email_address"), blank=True)
    is_done = models.BooleanField(_("is_done"), default=False)

    class Meta:
        db_table = 'sante\".\"st22_doctor_change_suggestion'
        verbose_name = _("St22DoctorChangeSuggestion")
        managed=False


class St23HealthSite(models.Model):
    """
    A named group of doctors based on their address. For instance, a hospital
    """
    site_name = models.CharField(_("site_name"), max_length=120)
    public_link = models.URLField(_("public_link"), blank=True, max_length=255)
    address = models.CharField(_("address"), max_length=255)
    appointment_link = models.CharField(_("appointment_link"), blank=True, null=True, max_length=2000)

    class Meta:
        db_table = 'sante\".\"st23_health_site'
        verbose_name = _("St23HealthSite")
        managed=False
    
    def __str__(self):
        return self.site_name
