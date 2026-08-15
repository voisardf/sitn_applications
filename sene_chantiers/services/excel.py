"""Dossier-wide Excel export.

Scope is the whole dossier, not a single report, even though the trigger
lives on one report's view: one general sheet, one sheet per visit in
lifecycle order, and one sheet of the emails actually sent.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..labels import email_status_label
from ..models import Appreciation, Conformity, EmailStatus

HEADER_FILL = PatternFill("solid", fgColor="1C2B4A")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
LABEL_FONT = Font(bold=True, size=10)
THIN = Side(style="thin", color="D9DEE7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# Row fill per appreciation, so a sheet reads at a glance. XLSX only:
# a CSV export could not carry this.
APPRECIATION_FILL = {
    Appreciation.VERT: PatternFill("solid", fgColor="E9F5EC"),
    Appreciation.JAUNE: PatternFill("solid", fgColor="FDF4E1"),
    Appreciation.ROUGE: PatternFill("solid", fgColor="FDEAEA"),
}


def _text(value):
    """Resolve lazy translation proxies: openpyxl only accepts plain types."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    return str(value)


def _write_header(sheet, headers, row=1):
    for column, title in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=column, value=_text(title))
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[row].height = 22


def _autosize(sheet, minimum=10, maximum=60):
    for column in sheet.columns:
        longest = max(
            (len(str(cell.value)) for cell in column if cell.value is not None),
            default=0,
        )
        letter = get_column_letter(column[0].column)
        sheet.column_dimensions[letter].width = max(minimum, min(maximum, longest + 2))


def _pairs(sheet, pairs, start=1):
    for offset, (label, value) in enumerate(pairs):
        row = start + offset
        label_cell = sheet.cell(row=row, column=1, value=_text(label))
        label_cell.font = LABEL_FONT
        sheet.cell(row=row, column=2, value=_text(value))
    return start + len(pairs)


def _general_sheet(workbook, chantier):
    sheet = workbook.active
    sheet.title = "Informations générales"
    _pairs(sheet, [
        ("N° SATAC", chantier.satac_number),
        ("Chantier", chantier.site_name),
        ("Adresse", chantier.adresse),
        ("Commune", chantier.commune.comnom if chantier.commune else ""),
        ("Maître d'ouvrage", chantier.maitre_ouvrage),
        ("E-mail maître d'ouvrage", chantier.maitre_ouvrage_email),
        ("Entreprise générale", chantier.entreprise_generale or "—"),
        ("Date de création", chantier.created_at.strftime("%d.%m.%Y")),
    ])
    _autosize(sheet, minimum=22)


def _control_report_sheet(workbook, report):
    sheet = workbook.create_sheet("Contrôle initial")
    fill = APPRECIATION_FILL.get(report.global_appreciation)

    next_row = _pairs(sheet, [
        ("Date du contrôle", report.control_date.strftime("%d.%m.%Y")),
        ("Conditions météo", report.weather_condition.label
         if report.weather_condition else ""),
        ("Température (°C)", report.temperature),
        ("Phase des travaux", report.construction_phase.label
         if report.construction_phase else ""),
        ("Appréciation globale", report.get_global_appreciation_display()),
        ("Prochain contrôle", report.next_control_date.strftime("%d.%m.%Y")
         if report.next_control_date else "—"),
        ("Inspecteur", report.inspector.get_full_name()
         or report.inspector.get_username()),
    ]) + 1

    sheet.cell(row=next_row, column=1, value="Synthèse par thème").font = LABEL_FONT
    next_row += 1
    _write_header(sheet, ["Thème", "Appréciation", "Points contrôlés",
                          "Remarques principales", "Observations"], row=next_row)

    answers = list(report.control_point_answers.select_related("control_point"))
    by_theme = {}
    for answer in answers:
        by_theme.setdefault(answer.control_point.theme_id, []).append(answer)

    for assessment in report.theme_assessments.select_related("theme"):
        next_row += 1
        theme_answers = by_theme.get(assessment.theme_id, [])
        checked = sum(
            1 for a in theme_answers
            if a.conformity and a.conformity != Conformity.NOT_APPLICABLE
        )
        values = [
            assessment.theme.label,
            assessment.get_appreciation_display(),
            f"{checked} / {len(theme_answers)}",
            assessment.synthesis_remarks,
            assessment.detail_observations,
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=next_row, column=column, value=_text(value))
            cell.border = BORDER
            if fill:
                cell.fill = fill

    next_row += 2
    sheet.cell(row=next_row, column=1, value="Mesures à prendre").font = LABEL_FONT
    next_row += 1
    _write_header(sheet, ["N°", "Mesure", "Responsable", "Échéance", "Statut"],
                  row=next_row)
    for measure in report.corrective_measures.all():
        next_row += 1
        values = [measure.order, measure.description, measure.responsible,
                  measure.deadline.strftime("%d.%m.%Y"),
                  measure.get_status_display()]
        for column, value in enumerate(values, start=1):
            sheet.cell(row=next_row, column=column,
                       value=_text(value)).border = BORDER

    next_row += 2
    sheet.cell(row=next_row, column=1, value="Détail des thèmes").font = LABEL_FONT
    next_row += 1
    _write_header(sheet, ["Thème", "Point contrôlé", "Conformité"], row=next_row)
    for answer in answers:
        next_row += 1
        values = [answer.control_point.theme.label, answer.control_point.label,
                  answer.get_conformity_display() if answer.conformity else "—"]
        for column, value in enumerate(values, start=1):
            sheet.cell(row=next_row, column=column,
                       value=_text(value)).border = BORDER

    next_row += 2
    _pairs(sheet, [
        ("Observations générales", report.observations_generales),
        ("Procédure de contrôle", report.procedure_controle),
    ], start=next_row)
    _autosize(sheet)


def _followup_sheet(workbook, report, index):
    sheet = workbook.create_sheet(f"Suivi {index}")
    fill = APPRECIATION_FILL.get(report.global_appreciation)

    next_row = _pairs(sheet, [
        ("Date du suivi", report.follow_up_date.strftime("%d.%m.%Y")),
        ("Appréciation globale", report.get_global_appreciation_display()),
        ("Prochain contrôle", report.next_control_date.strftime("%d.%m.%Y")
         if report.next_control_date else "—"),
        ("Dernier contrôle avant dénonciation",
         "Oui" if report.is_denunciation_escalation else "Non"),
        ("État de clôture", report.get_final_closure_state_display()
         if report.final_closure_state else "—"),
        ("Inspecteur", report.inspector.get_full_name()
         or report.inspector.get_username()),
    ]) + 1

    sheet.cell(row=next_row, column=1,
               value="Contrôle des mesures correctives").font = LABEL_FONT
    next_row += 1
    _write_header(sheet, ["N°", "Mesure demandée", "État précédent", "Constats",
                          "Statut", "Responsable", "Nouvelle échéance"],
                  row=next_row)
    for followup in report.measure_followups.select_related("original_measure"):
        next_row += 1
        values = [
            followup.original_measure.order,
            followup.original_measure.description,
            followup.get_state_at_previous_control_display()
            if followup.state_at_previous_control else "—",
            followup.findings,
            followup.get_status_display(),
            followup.responsible,
            followup.new_deadline.strftime("%d.%m.%Y")
            if followup.new_deadline else "—",
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=next_row, column=column, value=_text(value))
            cell.border = BORDER
            if fill:
                cell.fill = fill

    next_row += 2
    _pairs(sheet, [("Nouvelles anomalies", report.new_anomalies_description or "—")],
           start=next_row)
    _autosize(sheet)


def _emails_sheet(workbook, chantier):
    sheet = workbook.create_sheet("Courriels envoyés")
    _write_header(sheet, ["Date d'envoi", "Statut", "Modèle", "Destinataire",
                          "Objet", "Pièces jointes"])
    row = 1
    sent = chantier.email_records.filter(status=EmailStatus.SENT).order_by("sent_at")
    for record in sent:
        row += 1
        values = [
            record.sent_at.strftime("%d.%m.%Y %H:%M") if record.sent_at else "",
            email_status_label(record.template_used),
            record.get_template_used_display(),
            record.recipient_email,
            record.subject,
            record.selected_photos.count(),
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(row=row, column=column,
                       value=_text(value)).border = BORDER
    if row == 1:
        sheet.cell(row=2, column=1, value="Aucun courriel envoyé pour ce dossier.")
    _autosize(sheet)


def dossier_workbook(chantier):
    """Build the whole-dossier workbook and return it as bytes."""
    workbook = Workbook()
    _general_sheet(workbook, chantier)

    control_report = getattr(chantier, "control_report", None)
    if control_report:
        _control_report_sheet(workbook, control_report)

    followups = chantier.corrective_measure_reports.order_by("follow_up_date", "pk")
    for index, followup in enumerate(followups, start=1):
        _followup_sheet(workbook, followup, index)

    _emails_sheet(workbook, chantier)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
