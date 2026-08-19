"""Data model for the sene_chantiers application.

Identifiers are English; user-facing labels are French via gettext_lazy.
Tables live in the dedicated `sene_chantiers` PostgreSQL schema, using the
same db_table quoting convention as the ppe app.

Cross-row rules, enforced at the view/formset layer, not here:
    Three rules below check whether a SET of child rows meets some
    condition, rather than a single row's own fields — CorrectiveMeasure
    (>=1 row when the report is not `vert`), ThemeAssessment (exactly one
    row per Theme per report), and ControlPointAnswer (exactly one row
    per ControlPoint per report). None of these can be a Model.clean() on
    the parent: on creation the parent has no id yet for children to
    reference, and on edit, clean() runs before the formset that actually
    adds/removes child rows is processed. All three must be validated in
    the view, where the parent form and its formset(s) are both in memory
    and individually valid but not yet saved. A second entry point now
    exists — the superuser-only admin in `admin.py` — and the checks did
    have to travel with it: two of the three are also database
    constraints and came for free, the third is re-implemented there.
    Any further entry point must do the same.
"""

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.search import SearchVectorField
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from cadastre.models import Commune

SCHEMA = 'sene_chantiers"."'

def sanitized_photo_storage():
    """Storage for the clean copies, under DOWNLOAD_ROOT.

    A callable rather than an instance: Django serialises the reference
    into migrations instead of the resolved path, which differs per
    environment (/data in Docker, a local folder for runserver).

    /upload is writable by the web container; /data is mounted read-only
    there and written only by the photo worker container.
    """
    return FileSystemStorage(location=settings.DOWNLOAD_ROOT)

ALLOWED_PHOTO_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "heic"]


def photo_upload_path(instance, filename):
    """Photos are grouped per dossier: <root>/sene_chantiers/<satac>/<file>."""
    return f"sene_chantiers/{instance.satac_number}/{filename}"


def validate_photo_size(value):
    """Server-side size guard; the accept attribute is client-side only."""
    max_bytes = settings.SENE_CHANTIERS_PHOTO_MAX_SIZE_MB * 1024 * 1024
    if value.size > max_bytes:
        raise ValidationError(
            _("Le fichier image semble être trop volumineux ou contient une erreur.")
        )


# --------------------------------------------------------------------------
# Enumerations
#
# Values are fixed because the appreciation cascades depend on them; only
# the French labels below are translatable copy.
# --------------------------------------------------------------------------


class Appreciation(models.TextChoices):
    """The traffic light. Stored values stay the colour names because the
    cascades and the CSS modifiers key off them; the labels are what the
    inspector actually reads."""

    VERT = "vert", _("Conforme")
    JAUNE = "jaune", _("Écarts mineurs")
    ROUGE = "rouge", _("Non conforme")


class MeasureStatus(models.TextChoices):
    """Section 03 of the initial report."""

    OPEN = "open", _("Ouverte")
    IN_PROGRESS = "in_progress", _("En cours")
    CLOSED = "closed", _("Fermée")


class FollowUpStatus(models.TextChoices):
    """Section 02 of the follow-up report."""

    CLOSED = "closed", _("Fermée")
    OPEN = "open", _("Ouverte")
    NOT_DONE = "not_done", _("Non réalisée")


class Conformity(models.TextChoices):
    YES = "yes", _("Oui")
    NO = "no", _("Non")
    NOT_APPLICABLE = "na", _("N.A.")


class PhotoStatus(models.TextChoices):
    PENDING = "pending", _("En attente")
    PROCESSING = "processing", _("En cours de traitement")
    DONE = "done", _("Traitée")
    FAILED = "failed", _("Échec")


class EmailStatus(models.TextChoices):
    DRAFT = "draft", _("Brouillon")
    SENT = "sent", _("Envoyé")


class EmailTemplate(models.IntegerChoices):
    CONFORME = 1, _("Chantier conforme")
    NON_CONFORMITES = 2, _("Non-conformités avec délai de mise en conformité")
    LEVEE = 3, _("Levée de non-conformités après contrôle")
    ULTIME_DELAI = 4, _("Ultime délai de corrections")


class FinalClosureState(models.TextChoices):
    SELF_CORRECTED = "self_corrected", _("Mise en conformité par l'entreprise")
    AUTHORITY_ENFORCED = "authority_enforced", _("Exécution par l'autorité")


# --------------------------------------------------------------------------
# External / unmanaged reference tables
#
# Read-only, owned by other schemas of the same PostgreSQL server.
# cadastre.Commune is imported rather than redefined.
# --------------------------------------------------------------------------


class SearchSatac(models.Model):
    """FTS locator table. Carries geometry only, no permit attributes."""

    idobj = models.CharField(max_length=40, primary_key=True)
    instance_id = models.BigIntegerField()  # the SATAC number; filter on this
    state_code = models.CharField(max_length=20, blank=True, null=True)
    search_satac = models.CharField(max_length=30)  # label, "N° SATAC: 121463"
    geom = models.PointField(srid=settings.DEFAULT_SRID)
    _ts = SearchVectorField()
    actions = models.CharField(max_length=500)  # JSON as text; json.loads() it

    class Meta:
        managed = False
        db_table = 'searchtables"."search_satac'
        verbose_name = _("Recherche SATAC")

    def __str__(self):
        return self.search_satac


class At034AutorisationConstruire(models.Model):
    """Building-permit records. Single table on the internet instance."""

    idobj = models.CharField(max_length=40, primary_key=True)
    instance_id = models.BigIntegerField(null=True)  # the SATAC number
    coord_est = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    coord_nord = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    lien_avis = models.CharField(max_length=200, blank=True, null=True)
    lien_plan = models.CharField(max_length=200, blank=True, null=True)
    debut_enquete = models.DateField(null=True)
    fin_enquete = models.DateField(null=True)
    cadastre = models.CharField(max_length=200, blank=True, null=True)
    demande_permis = models.CharField(max_length=200, blank=True, null=True)
    categorie_ouvrage = models.CharField(max_length=200, blank=True, null=True)
    type_construction = models.CharField(max_length=200, blank=True, null=True)
    etat_dossier = models.CharField(max_length=200, blank=True, null=True)
    affichage = models.SmallIntegerField(null=True)
    document = models.CharField(max_length=5, blank=True, null=True)
    commune = models.CharField(max_length=100, blank=True, null=True)
    idcom = models.SmallIntegerField(null=True)  # equivalent to Commune.numcom
    is_sended = models.SmallIntegerField(null=True)
    d_reception = models.DateField(null=True)
    d_transmission = models.DateField(null=True)
    v_satac = models.SmallIntegerField(null=True)
    geom = models.PointField(srid=settings.DEFAULT_SRID)
    contact_cne = models.CharField(max_length=200, blank=True, null=True)
    demande = models.TextField(blank=True, null=True)
    no_fao = models.TextField(blank=True, null=True)
    parcelle = models.TextField(blank=True, null=True)
    requerant = models.TextField(blank=True, null=True)
    auteur_plan = models.TextField(blank=True, null=True)
    description_ouvrage = models.TextField(blank=True, null=True)
    zone = models.TextField(blank=True, null=True)
    resp_code = models.TextField(blank=True, null=True)
    decision_speciale = models.TextField(blank=True, null=True)
    situation = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'amenagement"."at034_autorisation_construire'
        verbose_name = _("Autorisation de construire")

    def __str__(self):
        return str(self.instance_id)


# --------------------------------------------------------------------------
# Admin-managed reference data
# --------------------------------------------------------------------------


class WeatherCondition(models.Model):
    label = models.CharField(_("Condition météo"), max_length=100, unique=True)
    order = models.PositiveSmallIntegerField(_("Ordre"), default=0)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        db_table = SCHEMA + "weather_condition"
        ordering = ["order", "label"]
        verbose_name = _("Condition météo")
        verbose_name_plural = _("Conditions météo")

    def __str__(self):
        return self.label


class ConstructionPhase(models.Model):
    label = models.CharField(_("Phase des travaux"), max_length=100, unique=True)
    order = models.PositiveSmallIntegerField(_("Ordre"), default=0)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        db_table = SCHEMA + "construction_phase"
        ordering = ["order", "label"]
        verbose_name = _("Phase des travaux")
        verbose_name_plural = _("Phases des travaux")

    def __str__(self):
        return self.label


class Theme(models.Model):
    """The five themes of sections 02 and 04. Seeded by data migration."""

    code = models.SlugField(_("Code"), max_length=30, unique=True)
    label = models.CharField(_("Thème"), max_length=100)
    order = models.PositiveSmallIntegerField(_("Ordre"), default=0)

    class Meta:
        db_table = SCHEMA + "theme"
        ordering = ["order", "label"]
        verbose_name = _("Thème")
        verbose_name_plural = _("Thèmes")

    def __str__(self):
        return self.label


class ControlPoint(models.Model):
    """Section 04 checklist item. Seeded by data migration."""

    theme = models.ForeignKey(
        Theme,
        on_delete=models.PROTECT,
        related_name="control_points",
        verbose_name=_("Thème"),
    )
    label = models.CharField(_("Point contrôlé"), max_length=250)
    order = models.PositiveSmallIntegerField(_("Ordre"), default=0)

    class Meta:
        db_table = SCHEMA + "control_point"
        ordering = ["theme__order", "order"]
        verbose_name = _("Point contrôlé")
        verbose_name_plural = _("Points contrôlés")

    def __str__(self):
        return self.label


# --------------------------------------------------------------------------
# Core entities
# --------------------------------------------------------------------------


class Chantier(models.Model):
    """A dossier, identified by its SATAC permit number."""

    satac_number = models.BigIntegerField(_("N° SATAC"), unique=True, db_index=True)
    site_name = models.CharField(_("Chantier"), max_length=250)
    adresse = models.CharField(_("Adresse"), max_length=250)
    # db_constraint=False: Commune is unmanaged and lives in a shared schema
    # this app must not constrain. Resolved from at034.idcom == Commune.numcom.
    commune = models.ForeignKey(
        Commune,
        on_delete=models.PROTECT,
        db_constraint=False,
        related_name="+",
        verbose_name=_("Commune"),
    )
    maitre_ouvrage = models.CharField(_("Maître d'ouvrage"), max_length=250)
    maitre_ouvrage_email = models.EmailField(_("E-Mail maître d'ouvrage"))
    entreprise_generale = models.CharField(
        _("Entreprise générale"), max_length=250, blank=True
    )
    # From SearchSatac.geom; null for manually created dossiers. Only used to
    # pick the nearest MeteoSwiss station.
    geom = models.PointField(
        _("Localisation"), srid=settings.DEFAULT_SRID, null=True, blank=True
    )
    created_at = models.DateTimeField(_("Date création"), auto_now_add=True)

    history = HistoricalRecords(table_name=SCHEMA + "chantier_history")

    class Meta:
        db_table = SCHEMA + "chantier"
        ordering = ["-created_at"]
        verbose_name = _("Chantier")
        verbose_name_plural = _("Chantiers")

    def __str__(self):
        return f"{self.satac_number} — {self.site_name}"

    @property
    def latest_report(self):
        """The most recent visit: the last follow-up, else the initial one."""
        latest = self.corrective_measure_reports.order_by(
            "-follow_up_date", "-pk"
        ).first()
        return latest or getattr(self, "control_report", None)

    @property
    def is_compliant(self):
        """The most recent concluded visit found the site compliant.

        No further corrective-measures follow-up may be opened while this
        holds. It is not yet a closure: the report stays editable until its
        notification email goes out, so an inspector who marked a measure
        compliant by mistake can correct it — which turns the appreciation
        back and reopens the cycle.

        Requires an actual finding, not merely a `vert` value: a
        freshly created report carries `vert` as its field default and would
        otherwise suspend the cycle before anything had been filled in.
        """
        report = self.latest_report
        return bool(report and report.closes_the_case and report.is_concluded)

    @property
    def is_closed(self):
        """Compliant *and* communicated: the notification email is sent.

        Sending locks the report, so from here nothing in the application
        can reopen the cycle — this is the end of the dossier. The one
        exception is out-of-band: a superuser may repair the report
        through the admin, unless the dossier has escalated towards a
        denunciation. See `has_entered_denunciation_track`.
        """
        return self.is_compliant and self.latest_report.is_locked

    @property
    def has_entered_denunciation_track(self):
        """The dossier has escalated towards the Ministère public.

        True from the moment a visit is flagged as the last control before
        denunciation — the *ultime délai* letter — and it stays true
        afterwards, including on the mandatory final visit that carries a
        `final_closure_state`.

        This is deliberately the earliest signal rather than the strictest
        one. The model has no "denunciation filed on <date>" field, so the
        escalation flag is the only marker available before the final
        visit is recorded, which is precisely the window in which the file
        is being handed over and must not be altered. It therefore also
        covers dossiers where the threat was made but no denunciation
        followed; see `sene_chantiers.admin` for what it gates.
        """
        return self.corrective_measure_reports.filter(
            Q(is_denunciation_escalation=True)
            | Q(final_closure_state__isnull=False, final_closure_state__gt="")
        ).exists()


class BaseReport(models.Model):
    """Fields shared by both report types. No table of its own."""

    global_appreciation = models.CharField(
        _("Appréciation globale"),
        max_length=10,
        choices=Appreciation,
        default=Appreciation.VERT,
    )
    global_appreciation_is_manual_override = models.BooleanField(
        _("Appréciation modifiée manuellement"), default=False
    )
    next_control_date = models.DateField(
        _("Prochain contrôle prévu"), null=True, blank=True
    )
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(class)ss",
        verbose_name=_("Inspecteur SENE"),
    )
    signature_date = models.DateField(_("Date de signature"), null=True, blank=True)
    # Set when the report's EmailRecord is sent; freezes the whole report.
    is_locked = models.BooleanField(_("Verrouillé"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    # Set by the forms when "Enregistrer le brouillon" is used. A draft is
    # incomplete by definition, so the *completeness* rules below do not
    # apply to it. Correctness rules — a control date in the future — still
    # do: a wrong value is wrong whether it is stored as a draft or not.
    # Without this distinction the model's own clean() re-imposes, through
    # ModelForm._post_clean(), exactly what the draft form just relaxed,
    # and the save fails silently.
    is_draft = False

    @property
    def closes_the_case(self):
        return self.global_appreciation == Appreciation.VERT

    def clean(self):
        super().clean()
        # "Délai de mise en conformité" — required unless the case closes here.
        if self.is_draft:
            return
        if not self.closes_the_case and not self.next_control_date:
            raise ValidationError(
                {
                    "next_control_date": _(
                        "Le prochain contrôle est obligatoire tant que le "
                        "chantier n'est pas conforme."
                    )
                }
            )


class ControlReport(BaseReport):
    """Rapport de contrôle environnemental — the initial visit."""

    chantier = models.OneToOneField(
        Chantier,
        on_delete=models.CASCADE,
        related_name="control_report",
        verbose_name=_("Chantier"),
    )
    control_date = models.DateField(_("Date du contrôle"))
    weather_condition = models.ForeignKey(
        WeatherCondition,
        on_delete=models.PROTECT,
        related_name="control_reports",
        verbose_name=_("Conditions météo"),
    )
    temperature = models.DecimalField(
        _("Température (°C)"),
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(-50), MaxValueValidator(60)],
    )
    construction_phase = models.ForeignKey(
        ConstructionPhase,
        on_delete=models.PROTECT,
        related_name="control_reports",
        verbose_name=_("Phase des travaux"),
    )
    observations_generales = models.TextField(_("Observations générales"), blank=True)
    procedure_controle = models.TextField(_("Procédure de contrôle"), blank=True)

    history = HistoricalRecords(table_name=SCHEMA + "control_report_history")

    class Meta:
        db_table = SCHEMA + "control_report"
        verbose_name = _("Rapport de contrôle environnemental")
        verbose_name_plural = _("Rapports de contrôle environnemental")

    def __str__(self):
        return f"Contrôle initial du {self.control_date}"

    @property
    def is_concluded(self):
        """True once the section 04 checklist has started being answered."""
        return self.control_point_answers.exclude(conformity="").exists()

    def clean(self):
        super().clean()
        if self.control_date and self.control_date > timezone.localdate():
            raise ValidationError(
                {"control_date": _("La date du contrôle ne peut pas être future.")}
            )


class CorrectiveMeasureReport(BaseReport):
    """Rapport de suivi des mesures correctives — visit 2 onward."""

    chantier = models.ForeignKey(
        Chantier,
        on_delete=models.CASCADE,
        related_name="corrective_measure_reports",
        verbose_name=_("Chantier"),
    )
    # Null means this follow-up chains directly from the initial ControlReport.
    previous_followup = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="next_followups",
        verbose_name=_("Contrôle précédent"),
    )
    follow_up_date = models.DateField(_("Date du suivi"))
    new_anomalies_description = models.TextField(
        _("Nouvelles anomalies constatées"), blank=True
    )
    # Escalation is an inspector judgment call, never derived from severity.
    is_denunciation_escalation = models.BooleanField(
        _("Dernier contrôle avant dénonciation"), default=False
    )
    # Set only on the mandatory final visit that follows a denunciation.
    final_closure_state = models.CharField(
        _("État de clôture"),
        max_length=20,
        choices=FinalClosureState,
        blank=True,
        null=True,
    )

    history = HistoricalRecords(
        table_name=SCHEMA + "corrective_measure_report_history"
    )

    class Meta:
        db_table = SCHEMA + "corrective_measure_report"
        ordering = ["follow_up_date"]
        verbose_name = _("Rapport de suivi des mesures correctives")
        verbose_name_plural = _("Rapports de suivi des mesures correctives")

    def __str__(self):
        return f"Suivi du {self.follow_up_date}"

    @property
    def sequence_number(self):
        """Which follow-up this is within its dossier, counting from 1.

        Derived rather than stored: the position follows from the dates, and
        a stored counter would have to be maintained on every insertion and
        deletion. It names the report on screen, in the exports and in
        their filenames, so all four agree by construction.
        """
        siblings = (type(self).objects
                    .filter(chantier_id=self.chantier_id)
                    .order_by("follow_up_date", "pk")
                    .values_list("pk", flat=True))
        for position, pk in enumerate(siblings, start=1):
            if pk == self.pk:
                return position
        # Unsaved, or no longer in the dossier: it would be the next one.
        return len(siblings) + 1

    @property
    def is_concluded(self):
        """True once the re-checked measures carry the inspector's findings."""
        return self.measure_followups.exclude(findings="").exists()

    def clean(self):
        super().clean()
        if self.follow_up_date and self.follow_up_date > timezone.localdate():
            raise ValidationError(
                {"follow_up_date": _("La date du suivi ne peut pas être future.")}
            )


class ThemeAssessment(models.Model):
    """One theme's appreciation, shared by sections 02 and 04.

    Exactly one row per Theme (5 total) is expected per ControlReport.
    Completeness is a cross-row rule — see the module docstring.
    """

    control_report = models.ForeignKey(
        ControlReport, on_delete=models.CASCADE, related_name="theme_assessments"
    )
    theme = models.ForeignKey(
        Theme, on_delete=models.PROTECT, related_name="assessments"
    )
    appreciation = models.CharField(
        _("Appréciation"),
        max_length=10,
        choices=Appreciation,
        default=Appreciation.VERT,
    )
    synthesis_remarks = models.TextField(_("Remarques principales"), blank=True)
    detail_observations = models.TextField(_("Observations"), blank=True)

    history = HistoricalRecords(table_name=SCHEMA + "theme_assessment_history")

    class Meta:
        db_table = SCHEMA + "theme_assessment"
        ordering = ["theme__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["control_report", "theme"], name="unique_theme_per_report"
            )
        ]
        verbose_name = _("Appréciation par thème")
        verbose_name_plural = _("Appréciations par thème")

    def __str__(self):
        return f"{self.theme} — {self.get_appreciation_display()}"


class ControlPointAnswer(models.Model):
    """Section 04 checklist answer. N.A. is a complete answer.

    Exactly one row per ControlPoint is expected per ControlReport.
    Completeness is a cross-row rule — see the module docstring.
    """

    control_report = models.ForeignKey(
        ControlReport, on_delete=models.CASCADE, related_name="control_point_answers"
    )
    control_point = models.ForeignKey(
        ControlPoint, on_delete=models.PROTECT, related_name="answers"
    )
    conformity = models.CharField(_("Conformité"), max_length=3, choices=Conformity)

    history = HistoricalRecords(table_name=SCHEMA + "control_point_answer_history")

    class Meta:
        db_table = SCHEMA + "control_point_answer"
        ordering = ["control_point__theme__order", "control_point__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["control_report", "control_point"],
                name="unique_control_point_per_report",
            )
        ]
        verbose_name = _("Réponse de conformité")
        verbose_name_plural = _("Réponses de conformité")

    def __str__(self):
        return f"{self.control_point} — {self.get_conformity_display()}"


class CorrectiveMeasure(models.Model):
    """Section 03 of the initial report.

    Required as a set: >=1 row when the report's global_appreciation is not
    `vert`, 0 rows valid when it is. Completeness is a cross-row rule — see
    the module docstring.
    """

    control_report = models.ForeignKey(
        ControlReport, on_delete=models.CASCADE, related_name="corrective_measures"
    )
    # Generated, never typed: the number is the row's position in the list.
    # `_save_measures()` assigns it, so it is absent from the form.
    order = models.PositiveSmallIntegerField(_("No."))
    description = models.TextField(_("Mesure"))
    responsible = models.CharField(_("Responsable"), max_length=250)
    # Nullable so a half-typed measure survives "Enregistrer le brouillon":
    # a draft is allowed to be incomplete, and a NOT NULL column would make
    # the row impossible to store at all. Still required by the form on a
    # real save (spec 4.2).
    deadline = models.DateField(_("Échéance"), null=True, blank=True)
    status = models.CharField(
        _("Statut"), max_length=15, choices=MeasureStatus, default=MeasureStatus.OPEN
    )

    history = HistoricalRecords(table_name=SCHEMA + "corrective_measure_history")

    class Meta:
        db_table = SCHEMA + "corrective_measure"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["control_report", "order"], name="unique_measure_order"
            )
        ]
        verbose_name = _("Mesure à prendre")
        verbose_name_plural = _("Mesures à prendre")

    def __str__(self):
        return f"{self.order}. {self.description[:60]}"


class MeasureFollowUp(models.Model):
    """Section 02 of a follow-up report: one original measure, re-checked."""

    corrective_measure_report = models.ForeignKey(
        CorrectiveMeasureReport,
        on_delete=models.CASCADE,
        related_name="measure_followups",
    )
    # Always the Section 03 row of the initial report, however many
    # follow-ups have happened since.
    original_measure = models.ForeignKey(
        CorrectiveMeasure, on_delete=models.PROTECT, related_name="followups"
    )
    state_at_previous_control = models.CharField(
        _("État lors du contrôle précédent"),
        max_length=15,
        choices=FollowUpStatus,
        blank=True,
    )
    findings = models.TextField(_("Constats lors du contrôle de suivi"))
    status = models.CharField(_("Statut"), max_length=15, choices=FollowUpStatus)
    responsible = models.CharField(_("Responsable"), max_length=250, blank=True)
    new_deadline = models.DateField(_("Nouvelle échéance"), null=True, blank=True)

    history = HistoricalRecords(table_name=SCHEMA + "measure_followup_history")

    class Meta:
        db_table = SCHEMA + "measure_followup"
        ordering = ["original_measure__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["corrective_measure_report", "original_measure"],
                name="unique_measure_per_followup",
            )
        ]
        verbose_name = _("Suivi de mesure")
        verbose_name_plural = _("Suivis de mesures")

    def __str__(self):
        return f"{self.original_measure} — {self.get_status_display()}"

    # See BaseReport.is_draft: the rule below states what a *finished* row
    # must satisfy, not what a half-typed one may hold.
    is_draft = False

    def clean(self):
        super().clean()
        if self.is_draft:
            return
        if self.status != FollowUpStatus.CLOSED and not self.new_deadline:
            raise ValidationError(
                {
                    "new_deadline": _(
                        "Une nouvelle échéance est requise tant que la mesure "
                        "n'est pas fermée."
                    )
                }
            )


class Photo(models.Model):
    """Attaches to exactly one report of either type.

    Two-stage storage: raw_upload lands in /upload, the worker container
    sanitizes it and writes the result to /data, then clears raw_upload.
    """

    control_report = models.ForeignKey(
        ControlReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="photos",
    )
    corrective_measure_report = models.ForeignKey(
        CorrectiveMeasureReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="photos",
    )
    raw_upload = models.FileField(
        _("Fichier déposé"),
        upload_to=photo_upload_path,
        blank=True,
        validators=[
            FileExtensionValidator(ALLOWED_PHOTO_EXTENSIONS),
            validate_photo_size,
        ],
    )
    image = models.FileField(
        _("Photo"),
        storage=sanitized_photo_storage,
        upload_to=photo_upload_path,
        blank=True,
    )
    caption = models.TextField(_("Remarques"), blank=True)
    order = models.PositiveSmallIntegerField(_("Ordre"), default=0)
    status = models.CharField(
        max_length=15, choices=PhotoStatus, default=PhotoStatus.PENDING
    )
    error_message = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords(table_name=SCHEMA + "photo_history")

    class Meta:
        db_table = SCHEMA + "photo"
        ordering = ["order", "uploaded_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(control_report__isnull=False,
                      corrective_measure_report__isnull=True)
                    | Q(control_report__isnull=True,
                        corrective_measure_report__isnull=False)
                ),
                name="photo_belongs_to_exactly_one_report",
            )
        ]
        verbose_name = _("Photo")
        verbose_name_plural = _("Photos")

    def __str__(self):
        return f"Photo {self.pk}"

    @property
    def report(self):
        return self.control_report or self.corrective_measure_report

    @property
    def satac_number(self):
        return self.report.chantier.satac_number


class EmailRecord(models.Model):
    """A generated notification email, draft or sent.

    The chantier FK is what makes template 4's "most recent email sent for
    this dossier" a single query.
    """

    chantier = models.ForeignKey(
        Chantier, on_delete=models.CASCADE, related_name="email_records"
    )
    control_report = models.ForeignKey(
        ControlReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="email_records",
    )
    corrective_measure_report = models.ForeignKey(
        CorrectiveMeasureReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="email_records",
    )
    template_used = models.IntegerField(_("Modèle"), choices=EmailTemplate)
    recipient_email = models.EmailField(_("Destinataire"))
    subject = models.CharField(_("Objet"), max_length=250)
    body = models.TextField(_("Message"))
    # The PDF is regenerated at send time and attached in memory, never stored.
    selected_photos = models.ManyToManyField(
        Photo,
        blank=True,
        related_name="email_records",
        verbose_name=_("Pièces jointes"),
    )
    status = models.CharField(
        _("Statut"), max_length=10, choices=EmailStatus, default=EmailStatus.DRAFT
    )
    created_at = models.DateTimeField(_("Date de création"), auto_now_add=True)
    sent_at = models.DateTimeField(_("Date d'envoi"), null=True, blank=True)

    # selected_photos is deliberately not m2m-historised: drafts carry no
    # version history by design, and a sent record's attachment list is
    # immutable current state rather than something that changes over time.
    history = HistoricalRecords(table_name=SCHEMA + "email_record_history")

    class Meta:
        db_table = SCHEMA + "email_record"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(control_report__isnull=False,
                      corrective_measure_report__isnull=True)
                    | Q(control_report__isnull=True,
                        corrective_measure_report__isnull=False)
                ),
                name="email_belongs_to_exactly_one_report",
            )
        ]
        verbose_name = _("Courriel")
        verbose_name_plural = _("Courriels")

    def __str__(self):
        return f"{self.get_status_display()} — {self.subject}"

    @property
    def report(self):
        return self.control_report or self.corrective_measure_report

    @property
    def display_date(self):
        """Landing page "Date courriel": creation while draft, sent date after."""
        return self.sent_at or self.created_at
