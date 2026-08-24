"""Corrective-measure deadline tracking.

Two surfaces, one rule set: a weekly digest emailed to the inspectors who
own the measures, and live colouring wherever measures are listed. The
colouring is computed on read, so nothing has to be kept in step.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from ..models import (
    Chantier,
    CorrectiveMeasure,
    FollowUpStatus,
    MeasureFollowUp,
    MeasureStatus,
)

# A measure turns amber this many days before its deadline.
WARNING_DAYS = 2

OK = "ok"
DUE_SOON = "due_soon"
OVERDUE = "overdue"


def urgency(deadline, today=None):
    """Amber within two days of the deadline, red once it has passed."""
    if not deadline:
        return OK
    today = today or timezone.localdate()
    remaining = (deadline - today).days
    if remaining < 0:
        return OVERDUE
    if remaining <= WARNING_DAYS:
        return DUE_SOON
    return OK


def open_measures(today=None):
    """Measures still open whose deadline is near or past.

    Covers both surfaces the deadline lives on: the initial report's
    Section 03 rows, and the new deadlines set on a follow-up.
    """
    today = today or timezone.localdate()
    horizon = today + timedelta(days=WARNING_DAYS)

    initial = (
        CorrectiveMeasure.objects
        .exclude(status=MeasureStatus.CLOSED)
        .filter(deadline__lte=horizon)
        .select_related("control_report__chantier", "control_report__inspector")
    )
    followups = (
        MeasureFollowUp.objects
        .exclude(status=FollowUpStatus.CLOSED)
        .filter(new_deadline__isnull=False, new_deadline__lte=horizon)
        .select_related(
            "corrective_measure_report__chantier",
            "corrective_measure_report__inspector",
            "original_measure",
        )
    )
    return initial, followups


def _rows(today=None):
    """Flatten both sources into one comparable shape."""
    today = today or timezone.localdate()
    initial, followups = open_measures(today)
    rows = []

    for measure in initial:
        report = measure.control_report
        # A measure re-checked on a later visit is tracked there instead,
        # so the initial deadline no longer speaks for it.
        if measure.followups.exists():
            continue
        rows.append({
            "chantier": report.chantier,
            "inspector": report.inspector,
            "description": measure.description,
            "deadline": measure.deadline,
            "urgency": urgency(measure.deadline, today),
            "origin": "Contrôle initial",
        })

    for followup in followups:
        report = followup.corrective_measure_report
        rows.append({
            "chantier": report.chantier,
            "inspector": report.inspector,
            "description": followup.original_measure.description,
            "deadline": followup.new_deadline,
            "urgency": urgency(followup.new_deadline, today),
            "origin": "Suivi des mesures correctives",
        })

    rows.sort(key=lambda r: (r["deadline"], r["chantier"].satac_number))
    return rows


def by_inspector(today=None):
    """Group the pending measures by the inspector responsible."""
    grouped = {}
    for row in _rows(today):
        grouped.setdefault(row["inspector"], []).append(row)
    return grouped


def closures_by_inspector():
    grouped = {}
    for row in pending_closures():
        grouped.setdefault(row["inspector"], []).append(row)
    return grouped


def pending_closures():
    """Dossiers concluded compliant whose notification email is still unsent.

    Nothing else surfaces these: the measures are all closed, so the
    deadline rules above have nothing left to report, and the dossier
    would otherwise sit silently in that state forever. The closing
    email is what actually informs the maître d'ouvrage.
    """
    rows = []
    for chantier in Chantier.objects.select_related("commune"):
        if not chantier.is_compliant or chantier.is_closed:
            continue
        report = chantier.latest_report
        rows.append(
            {
                "chantier": chantier,
                "inspector": report.inspector,
                "since": getattr(report, "follow_up_date", None)
                or getattr(report, "control_date", None),
            }
        )
    rows.sort(key=lambda r: (r["since"], r["chantier"].satac_number))
    return rows


def banner_counts(today=None):
    """Totals for the in-app banner."""
    rows = _rows(today)
    closures = pending_closures()
    return {
        "overdue": sum(1 for r in rows if r["urgency"] == OVERDUE),
        "due_soon": sum(1 for r in rows if r["urgency"] == DUE_SOON),
        "pending_closure": len(closures),
        "rows": rows,
        "closures": closures,
    }


def _body(rows, closures, today):
    overdue = [r for r in rows if r["urgency"] == OVERDUE]
    soon = [r for r in rows if r["urgency"] == DUE_SOON]
    lines = [
        "Bonjour,",
        "",
        "Récapitulatif hebdomadaire du suivi de chantiers "
        f"au {today.strftime('%d.%m.%Y')}.",
        "",
    ]
    if overdue:
        lines.append(f"ÉCHÉANCE DÉPASSÉE ({len(overdue)})")
        for row in overdue:
            lines.append(
                f"  · SATAC {row['chantier'].satac_number} — "
                f"{row['chantier'].site_name} — échéance "
                f"{row['deadline'].strftime('%d.%m.%Y')} — "
                f"{row['description'][:80]}"
            )
        lines.append("")
    if soon:
        lines.append(f"ÉCHÉANCE PROCHE ({len(soon)})")
        for row in soon:
            lines.append(
                f"  · SATAC {row['chantier'].satac_number} — "
                f"{row['chantier'].site_name} — échéance "
                f"{row['deadline'].strftime('%d.%m.%Y')} — "
                f"{row['description'][:80]}"
            )
        lines.append("")
    if closures:
        lines.append(f"CHANTIER CONFORME, COURRIEL À ENVOYER ({len(closures)})")
        for row in closures:
            lines.append(
                f"  · SATAC {row['chantier'].satac_number} — "
                f"{row['chantier'].site_name} — conforme depuis le "
                f"{row['since'].strftime('%d.%m.%Y')}"
            )
        lines.append(
            "    Le dossier reste ouvert tant que le courriel de levée "
            "n'est pas envoyé."
        )
        lines.append("")
    lines.append("Ce message est généré automatiquement par sene_chantiers.")
    return "\n".join(lines)


def send_digest(today=None, dry_run=False):
    """Email each inspector their own pending measures.

    Returns the number of messages sent. Inspectors with nothing pending
    are not mailed at all, so a quiet week produces no noise.
    """
    today = today or timezone.localdate()
    measures = by_inspector(today)
    closures = closures_by_inspector()
    sent = 0
    for inspector in set(measures) | set(closures):
        if not inspector.email:
            continue
        rows = measures.get(inspector, [])
        inspector_closures = closures.get(inspector, [])
        parts = []
        if rows:
            parts.append(f"{len(rows)} mesure(s) à échéance")
        if inspector_closures:
            parts.append(f"{len(inspector_closures)} courriel(s) à envoyer")
        subject = "Suivi de chantiers — " + ", ".join(parts)
        message = EmailMessage(
            subject=subject,
            body=_body(rows, inspector_closures, today),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[inspector.email],
        )
        if not dry_run:
            message.send(fail_silently=False)
        sent += 1
    return sent
