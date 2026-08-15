"""Rebuild a small set of coherent demo dossiers.

Intended for a development or demonstration instance: it deletes the
dossiers it manages and recreates them, so the state shown to inspectors
tells a clear story rather than whatever testing left behind.

Refuses to run outside DEBUG, since it destroys dossiers.

The three dossiers cover the states an inspector meets in practice:

  1. conforme, courriel pas encore envoyé — le cycle est arrêté mais le
     rapport reste corrigeable, et le dossier apparaît dans les rappels ;
  2. écarts mineurs au contrôle initial, levés au second passage,
     courriel envoyé — dossier clos, cycle complet ;
  3. non conforme, puis écarts mineurs au suivi, prochain contrôle
     planifié — dossier actif, avec des échéances.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from cadastre.models import Commune
from sene_chantiers.models import (
    Appreciation,
    Chantier,
    Conformity,
    ConstructionPhase,
    ControlPoint,
    ControlPointAnswer,
    ControlReport,
    CorrectiveMeasure,
    CorrectiveMeasureReport,
    EmailRecord,
    EmailStatus,
    FollowUpStatus,
    MeasureFollowUp,
    MeasureStatus,
    Photo,
    SearchSatac,
    Theme,
    ThemeAssessment,
    WeatherCondition,
)
from sene_chantiers.services import emails

TODAY = timezone.localdate()

# Real permit numbers, so the SATAC lookup resolves; the site names,
# contacts and findings below are invented.
DOSSIERS = [
    {
        "satac": 123101,
        "site_name": "Réaménagement du secteur des Cadolles",
        "adresse": "Rue des Cadolles 12",
        "maitre_ouvrage": "Commune de Val-de-Ruz",
        "entreprise": "Exemple SA Construction",
        "scenario": "compliant_unsent",
    },
    {
        "satac": 120006,
        "site_name": "Rénovation d'une maison individuelle",
        "adresse": "Chemin des Vignes 4",
        "maitre_ouvrage": "M. et Mme Exemple",
        "entreprise": "Bâti Exemple Sàrl",
        "scenario": "minor_then_fixed",
    },
    {
        "satac": 120000,
        "site_name": "Construction d'un immeuble avec parking",
        "adresse": "Rue du Progrès 118",
        "maitre_ouvrage": "Société Immobilière Exemple",
        "entreprise": "Grands Travaux Exemple SA",
        "scenario": "active_minor",
    },
]


class Command(BaseCommand):
    help = "Recreate the demo dossiers (development instances only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--inspector",
            default="chantiers_admin",
            help="Username the demo reports are attributed to.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Refusé hors DEBUG : cette commande supprime des dossiers."
            )
        try:
            inspector = get_user_model().objects.get(
                username=options["inspector"]
            )
        except get_user_model().DoesNotExist:
            raise CommandError(
                f"Utilisateur « {options['inspector']} » introuvable."
            )

        with transaction.atomic():
            for spec in DOSSIERS:
                self._wipe(spec["satac"])
                chantier = self._chantier(spec)
                getattr(self, f"_{spec['scenario']}")(chantier, inspector)
                self.stdout.write(
                    f"  {spec['satac']} — {spec['scenario']}: "
                    f"conforme={chantier.is_compliant} clos={chantier.is_closed}"
                )
        self.stdout.write(self.style.SUCCESS("Dossiers de démonstration recréés."))

    # -- helpers ---------------------------------------------------------

    def _wipe(self, satac_number):
        """Remove a dossier and everything hanging off it, in FK order."""
        chantier = Chantier.objects.filter(satac_number=satac_number).first()
        if not chantier:
            return
        EmailRecord.objects.filter(chantier=chantier).delete()
        Photo.objects.filter(
            control_report__chantier=chantier
        ).delete()
        Photo.objects.filter(
            corrective_measure_report__chantier=chantier
        ).delete()
        MeasureFollowUp.objects.filter(
            corrective_measure_report__chantier=chantier
        ).delete()
        # previous_followup is PROTECT, so unwind the chain from its end.
        for followup in CorrectiveMeasureReport.objects.filter(
            chantier=chantier
        ).order_by("-pk"):
            followup.delete()
        CorrectiveMeasure.objects.filter(
            control_report__chantier=chantier
        ).delete()
        ControlPointAnswer.objects.filter(
            control_report__chantier=chantier
        ).delete()
        ThemeAssessment.objects.filter(
            control_report__chantier=chantier
        ).delete()
        ControlReport.objects.filter(chantier=chantier).delete()
        chantier.delete()

    def _chantier(self, spec):
        locator = SearchSatac.objects.filter(instance_id=spec["satac"]).first()
        return Chantier.objects.create(
            satac_number=spec["satac"],
            site_name=spec["site_name"],
            adresse=spec["adresse"],
            commune=Commune.objects.first(),
            maitre_ouvrage=spec["maitre_ouvrage"],
            maitre_ouvrage_email="francois.voisard@ne.ch",
            entreprise_generale=spec["entreprise"],
            geom=locator.geom if locator else None,
        )

    def _control_report(self, chantier, inspector, days_ago, appreciation,
                        next_control=None):
        report = ControlReport.objects.create(
            chantier=chantier,
            control_date=TODAY - timedelta(days=days_ago),
            weather_condition=WeatherCondition.objects.first(),
            construction_phase=ConstructionPhase.objects.first(),
            inspector=inspector,
            global_appreciation=appreciation,
            next_control_date=next_control,
            observations_generales="Visite de contrôle environnemental.",
            procedure_controle="Parcours du chantier et contrôle des points.",
        )
        # Section 02/04, answered so the visit counts as concluded.
        for theme in Theme.objects.all():
            ThemeAssessment.objects.create(
                control_report=report,
                theme=theme,
                appreciation=Appreciation.VERT,
                synthesis_remarks="R.A.S.",
                detail_observations="R.A.S.",
            )
        ControlPointAnswer.objects.bulk_create(
            [
                ControlPointAnswer(
                    control_report=report,
                    control_point=point,
                    conformity=Conformity.YES,
                )
                for point in ControlPoint.objects.all()
            ]
        )
        return report

    def _flag_theme(self, report, code, appreciation, remark, wrong_points=1):
        """Make one theme non-compliant, consistently with its checklist."""
        theme = Theme.objects.get(code=code)
        assessment = report.theme_assessments.get(theme=theme)
        assessment.appreciation = appreciation
        assessment.synthesis_remarks = remark
        assessment.detail_observations = remark
        assessment.save()
        answers = report.control_point_answers.filter(
            control_point__theme=theme
        )[:wrong_points]
        for answer in answers:
            answer.conformity = Conformity.NO
            answer.save()

    def _sent_email(self, chantier, report, template, inspector):
        subject, body = emails.render(report, template_id=template)
        # The XOR check constraint is enforced on insert, so the report
        # reference has to be part of the initial row.
        link = (
            {"control_report": report}
            if isinstance(report, ControlReport)
            else {"corrective_measure_report": report}
        )
        record = EmailRecord.objects.create(
            chantier=chantier,
            template_used=template,
            recipient_email=chantier.maitre_ouvrage_email,
            subject=subject,
            body=body,
            status=EmailStatus.SENT,
            sent_at=timezone.now(),
            **link,
        )
        report.is_locked = True
        report.save(update_fields=["is_locked"])
        return record

    # -- scenarios -------------------------------------------------------

    def _compliant_unsent(self, chantier, inspector):
        """Conforme au second passage, courriel pas encore parti."""
        report = self._control_report(
            chantier, inspector, days_ago=40, appreciation=Appreciation.ROUGE,
            next_control=TODAY - timedelta(days=5),
        )
        self._flag_theme(report, "dechets", Appreciation.ROUGE,
                         "Bennes non couvertes, tri incomplet.", wrong_points=2)
        self._flag_theme(report, "air", Appreciation.JAUNE,
                         "Poussières non maîtrisées par vent sec.")
        measure = CorrectiveMeasure.objects.create(
            control_report=report, order=1,
            description="Couvrir les bennes et rétablir le tri par catégorie",
            responsible="Grands Travaux Exemple SA",
            deadline=TODAY - timedelta(days=5),
            status=MeasureStatus.CLOSED,
        )
        self._sent_email(chantier, report, 2, inspector)

        followup = CorrectiveMeasureReport.objects.create(
            chantier=chantier, follow_up_date=TODAY - timedelta(days=2),
            inspector=inspector, global_appreciation=Appreciation.VERT,
        )
        MeasureFollowUp.objects.create(
            corrective_measure_report=followup,
            original_measure=measure,
            state_at_previous_control=FollowUpStatus.OPEN,
            findings="Bennes couvertes, tri conforme lors du passage.",
            status=FollowUpStatus.CLOSED,
            responsible="Grands Travaux Exemple SA",
        )
        # Pas de courriel : c'est tout l'intérêt de ce dossier.

    def _minor_then_fixed(self, chantier, inspector):
        """Écarts mineurs, levés au second passage, dossier clos."""
        report = self._control_report(
            chantier, inspector, days_ago=60, appreciation=Appreciation.JAUNE,
            next_control=TODAY - timedelta(days=25),
        )
        self._flag_theme(report, "eaux", Appreciation.JAUNE,
                         "Absence de protection des écoulements.")
        measure = CorrectiveMeasure.objects.create(
            control_report=report, order=1,
            description="Protéger les écoulements et installer un bac de "
                        "décantation",
            responsible="Bâti Exemple Sàrl",
            deadline=TODAY - timedelta(days=25),
            status=MeasureStatus.CLOSED,
        )
        self._sent_email(chantier, report, 2, inspector)

        followup = CorrectiveMeasureReport.objects.create(
            chantier=chantier, follow_up_date=TODAY - timedelta(days=20),
            inspector=inspector, global_appreciation=Appreciation.VERT,
            signature_date=TODAY - timedelta(days=20),
        )
        MeasureFollowUp.objects.create(
            corrective_measure_report=followup,
            original_measure=measure,
            state_at_previous_control=FollowUpStatus.OPEN,
            findings="Bac de décantation posé, écoulements protégés.",
            status=FollowUpStatus.CLOSED,
            responsible="Bâti Exemple Sàrl",
        )
        self._sent_email(chantier, followup, 3, inspector)

    def _active_minor(self, chantier, inspector):
        """Non conforme, puis écarts mineurs, prochain contrôle planifié."""
        report = self._control_report(
            chantier, inspector, days_ago=30, appreciation=Appreciation.ROUGE,
            next_control=TODAY - timedelta(days=10),
        )
        self._flag_theme(report, "sols", Appreciation.ROUGE,
                         "Produits polluants stockés hors rétention.",
                         wrong_points=2)
        self._flag_theme(report, "bruit", Appreciation.JAUNE,
                         "Travaux bruyants hors des horaires autorisés.")
        first = CorrectiveMeasure.objects.create(
            control_report=report, order=1,
            description="Placer les produits polluants sur bac de rétention",
            responsible="Grands Travaux Exemple SA",
            deadline=TODAY - timedelta(days=10),
            status=MeasureStatus.CLOSED,
        )
        second = CorrectiveMeasure.objects.create(
            control_report=report, order=2,
            description="Respecter les horaires de chantier",
            responsible="Grands Travaux Exemple SA",
            deadline=TODAY - timedelta(days=10),
            status=MeasureStatus.OPEN,
        )
        self._sent_email(chantier, report, 2, inspector)

        followup = CorrectiveMeasureReport.objects.create(
            chantier=chantier, follow_up_date=TODAY - timedelta(days=6),
            inspector=inspector, global_appreciation=Appreciation.JAUNE,
            next_control_date=TODAY + timedelta(days=1),
            new_anomalies_description="",
        )
        MeasureFollowUp.objects.create(
            corrective_measure_report=followup,
            original_measure=first,
            state_at_previous_control=FollowUpStatus.OPEN,
            findings="Bac de rétention en place.",
            status=FollowUpStatus.CLOSED,
            responsible="Grands Travaux Exemple SA",
        )
        MeasureFollowUp.objects.create(
            corrective_measure_report=followup,
            original_measure=second,
            state_at_previous_control=FollowUpStatus.OPEN,
            findings="Deux dépassements constatés depuis le dernier passage.",
            status=FollowUpStatus.OPEN,
            responsible="Grands Travaux Exemple SA",
            new_deadline=TODAY + timedelta(days=1),
        )
        self._sent_email(chantier, followup, 2, inspector)
