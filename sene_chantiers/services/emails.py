"""Notification emails.

The four templates are fixed copy confirmed with SENE; only the bracketed
values are substituted. The inspector may edit the result before sending,
so what is stored on the EmailRecord is the final text, not a template id
to re-render later.
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from ..models import (
    Appreciation,
    ControlReport,
    EmailRecord,
    EmailStatus,
    EmailTemplate,
)

SALUTATION = "Madame, Monsieur,"
CLOSING = (
    "Nous vous prions d'agréer, Madame, Monsieur, nos salutations "
    "distinguées."
)


def _fmt(value):
    return value.strftime("%d.%m.%Y") if value else "…"


def select_template(report):
    """Which of the four templates a report calls for.

    Template 4 is never selected automatically: escalation is a judgment
    call the inspector makes explicitly on a follow-up report.
    """
    if isinstance(report, ControlReport):
        return (
            EmailTemplate.CONFORME
            if report.global_appreciation == Appreciation.VERT
            else EmailTemplate.NON_CONFORMITES
        )
    if getattr(report, "is_denunciation_escalation", False):
        return EmailTemplate.ULTIME_DELAI
    return (
        EmailTemplate.LEVEE
        if report.global_appreciation == Appreciation.VERT
        else EmailTemplate.NON_CONFORMITES
    )


def non_conformity_summary(report):
    """The "[à compléter]" of template 2, derived from the report itself."""
    if not isinstance(report, ControlReport):
        followups = report.measure_followups.select_related("original_measure")
        open_items = [
            f.original_measure.description
            for f in followups
            if f.status != "closed"
        ]
        return " ; ".join(open_items) if open_items else "…"

    parts = []
    for assessment in report.theme_assessments.select_related("theme"):
        if assessment.appreciation != Appreciation.VERT:
            remark = assessment.synthesis_remarks.strip()
            parts.append(
                f"{assessment.theme.label} ({remark})" if remark
                else assessment.theme.label
            )
    for measure in report.corrective_measures.all():
        parts.append(measure.description.strip())
    return " ; ".join(p for p in parts if p) or "…"


def _last_sent_date(chantier):
    """Template 4 refers back to the previous notice actually sent."""
    previous = (
        EmailRecord.objects.filter(chantier=chantier, status=EmailStatus.SENT)
        .order_by("-sent_at")
        .first()
    )
    return _fmt(previous.sent_at.date()) if previous and previous.sent_at else "…"


def render(report, template_id=None):
    """Return (subject, body) for a report, ready for the inspector to edit."""
    chantier = report.chantier
    template_id = template_id or select_template(report)
    visit_date = _fmt(
        report.control_date if isinstance(report, ControlReport)
        else report.follow_up_date
    )
    street = chantier.adresse
    satac = chantier.satac_number
    deadline = _fmt(report.next_control_date)

    if template_id == EmailTemplate.CONFORME:
        subject = f"Suivi environnemental de chantier – Visite du {visit_date}"
        body = (
            f"{SALUTATION}\n\n"
            f"Suite à notre visite de chantier du {visit_date}, à {street} "
            f"(n° SATAC {satac}), nous avons constaté que les exigences "
            f"relatives à la protection de l'environnement sont pleinement "
            f"respectées sur le chantier.\n\n"
            f"Les mesures mises en place témoignent d'une bonne maîtrise des "
            f"aspects environnementaux et d'une réelle volonté de limiter les "
            f"impacts liés aux travaux. L'organisation observée et "
            f"l'implication de vos équipes contribuent au bon déroulement du "
            f"suivi environnemental ainsi qu'à la qualité globale du "
            f"chantier.\n\n"
            f"Vous trouverez en annexe le rapport de suivi environnemental "
            f"relatif à cette visite. Nous vous remercions pour la qualité de "
            f"votre collaboration.\n\n{CLOSING}"
        )

    elif template_id == EmailTemplate.NON_CONFORMITES:
        subject = "Constat de non-conformités – Demande de mise en conformité"
        body = (
            f"{SALUTATION}\n\n"
            f"Suite à notre visite de chantier du {visit_date}, à {street} "
            f"(n° SATAC {satac}), plusieurs éléments relatifs aux exigences de "
            f"protection de l'environnement ont été constatés comme non "
            f"conformes aux prescriptions en vigueur. Ces écarts concernent "
            f"notamment : {non_conformity_summary(report)}.\n\n"
            f"Ces situations ne sont pas compatibles avec les exigences "
            f"environnementales applicables au chantier et nécessitent une "
            f"remise en conformité dans les meilleurs délais. Nous vous prions "
            f"de bien vouloir prendre les mesures correctives nécessaires afin "
            f"de rétablir une situation conforme aux exigences en vigueur.\n\n"
            f"Un délai est fixé au {deadline} pour la mise en conformité "
            f"complète de l'ensemble des points relevés. À l'issue de ce délai, "
            f"une nouvelle vérification pourra être effectuée sur site.\n\n"
            f"Vous trouverez en annexe le rapport de suivi environnemental "
            f"relatif à cette visite. Nous vous remercions par avance pour "
            f"votre diligence et pour les actions que vous entreprendrez afin "
            f"de garantir le respect des exigences environnementales.\n\n"
            f"{CLOSING}"
        )

    elif template_id == EmailTemplate.LEVEE:
        subject = "Contrôle de suivi – Levée des non-conformités"
        body = (
            f"{SALUTATION}\n\n"
            f"Suite à notre visite de chantier du {visit_date}, à {street} "
            f"(n° SATAC {satac}), et au délai de remise en conformité fixé, "
            f"nous sommes repassés sur site en date de ce jour.\n\n"
            f"Nous vous remercions d'avoir mis en œuvre les mesures "
            f"correctives permettant de lever les non-conformités relevées "
            f"lors de notre précédent passage, telles que mentionnées dans "
            f"notre rapport de suivi environnemental annexé à notre précédent "
            f"envoi. Les points identifiés sont désormais conformes aux "
            f"exigences environnementales.\n\n"
            f"Dans une perspective d'amélioration continue, nous vous invitons "
            f"néanmoins à porter une attention particulière à ces aspects sur "
            f"vos futurs projets, afin d'éviter la réapparition de "
            f"non-conformités similaires.\n\n"
            f"Nous vous remercions pour votre collaboration et votre "
            f"réactivité dans le traitement de ces éléments.\n\n{CLOSING}"
        )

    else:  # ULTIME_DELAI
        subject = "Dernier délai de mise en conformité"
        body = (
            f"{SALUTATION}\n\n"
            f"Nous faisons suite à notre courriel en date du "
            f"{_last_sent_date(chantier)}, dans lequel plusieurs "
            f"non-conformités avaient été signalées sur le chantier, "
            f"accompagnées d'un délai à respecter pour leur correction.\n\n"
            f"Lors de notre récente visite sur site, nous avons constaté que "
            f"les mesures correctives demandées n'ont toujours pas été mises "
            f"en œuvre à ce jour.\n\n"
            f"Nous vous accordons un ultime délai afin que l'ensemble des "
            f"corrections soit réalisé. À défaut, nous serons malheureusement "
            f"contraints de procéder à une dénonciation formelle auprès des "
            f"autorités compétentes, conformément à la réglementation en "
            f"vigueur.\n\n"
            f"Délai de mise en conformité : jusqu'au {deadline}.\n\n"
            f"Nous vous remercions de prendre les dispositions nécessaires "
            f"sans tarder et vous remercions par avance pour votre "
            f"collaboration.\n\n{CLOSING}"
        )

    return subject, body


def attachment_budget(record):
    """Total size of the selected photos against the advisory limit."""
    total = 0
    for photo in record.selected_photos.all():
        if photo.image:
            try:
                total += photo.image.size
            except OSError:
                pass
    limit = settings.SENE_CHANTIERS_EMAIL_ATTACHMENTS_MAX_SIZE_MB * 1024 * 1024
    return {
        "bytes": total,
        "megabytes": round(total / (1024 * 1024), 2),
        "limit_mb": settings.SENE_CHANTIERS_EMAIL_ATTACHMENTS_MAX_SIZE_MB,
        "over_limit": total > limit,
    }


def send(record, pdf_bytes=None):
    """Send the record via SMTP and freeze the report it belongs to.

    The PDF is attached from memory; it is regenerated per send and never
    stored, since /data is read-only for the web container.
    """
    message = EmailMessage(
        subject=record.subject,
        body=record.body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[record.recipient_email],
    )
    if pdf_bytes:
        message.attach(
            f"rapport_{record.chantier.satac_number}.pdf",
            pdf_bytes,
            "application/pdf",
        )
    for photo in record.selected_photos.all():
        if not photo.image:
            continue
        photo.image.open("rb")
        message.attach(
            photo.image.name.rsplit("/", 1)[-1], photo.image.read(), "image/jpeg"
        )
        photo.image.close()

    message.send(fail_silently=False)

    record.status = EmailStatus.SENT
    record.sent_at = timezone.now()
    record.save(update_fields=["status", "sent_at"])

    # Sending is what settles a report: it becomes read-only from here.
    report = record.report
    if report and not report.is_locked:
        report.is_locked = True
        report.save(update_fields=["is_locked"])
    return record
