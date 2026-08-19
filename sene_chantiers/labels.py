"""Display labels for the traffic-light states.

Two vocabularies deliberately coexist, as drawn in the mockups: the
dossier and report pills describe the finding, while the Courriels column
describes what the email asks the recipient to do. The first comes
straight from the Appreciation choices; only the second needs a mapping.
"""

from django.utils.translation import gettext_lazy as _

from .models import Appreciation, EmailTemplate

# Courriels list — describes the action requested, so the `jaune` case
# reads as "Mesures à prendre" here rather than "Écarts mineurs".
EMAIL_TEMPLATE_LABELS = {
    EmailTemplate.CONFORME: _("Conforme"),
    EmailTemplate.NON_CONFORMITES: _("Mesures à prendre"),
    EmailTemplate.LEVEE: _("Conforme"),
    EmailTemplate.ULTIME_DELAI: _("Non conforme"),
}

# Which pill colour each email template carries.
EMAIL_TEMPLATE_APPRECIATION = {
    EmailTemplate.CONFORME: Appreciation.VERT,
    EmailTemplate.NON_CONFORMITES: Appreciation.JAUNE,
    EmailTemplate.LEVEE: Appreciation.VERT,
    EmailTemplate.ULTIME_DELAI: Appreciation.ROUGE,
}


# The long-form sentence printed beside each level in the PDF's
# "appréciation globale" card. Confirmed copy (Decision #2); the wording
# differs between the two report types because one judges the site and the
# other judges the measures.
APPRECIATION_DESCRIPTIONS = {
    "control": {
        Appreciation.VERT: _("Le chantier respecte les exigences légales."),
        Appreciation.JAUNE: _("Certains aspects ne sont pas maîtrisés mais "
                              "sans conséquence majeure."),
        Appreciation.ROUGE: _("Non-conformités établies, à corriger "
                              "rapidement."),
    },
    "followup": {
        Appreciation.VERT: _("Toutes les mesures correctives ont été "
                             "réalisées."),
        Appreciation.JAUNE: _("Une partie des mesures a été réalisée. Des "
                              "compléments restent à effectuer."),
        Appreciation.ROUGE: _("Les mesures n'ont pas été réalisées ou "
                              "demeurent insuffisantes."),
    },
}


# Second line of the follow-up conclusion box, shown on the web form only:
# it says what happens next, which the PDF states elsewhere. The first line
# is the confirmed sentence in APPRECIATION_DESCRIPTIONS above.
CONCLUSION_DETAIL = {
    Appreciation.VERT: _("Les non-conformités relevées sont levées."),
    Appreciation.JAUNE: _("Un nouveau contrôle est prévu afin de vérifier "
                          "la mise en conformité complète."),
    Appreciation.ROUGE: _("Un nouveau contrôle est prévu afin de vérifier "
                          "la mise en conformité."),
}


def followup_conclusion_lines():
    """The conclusion box text, keyed by appreciation value.

    Served to the page as data so the form's live preview and the PDF read
    from one definition. They were previously duplicated in a JS literal
    and had already drifted apart, one saying "restent insuffisantes"
    where the other said "demeurent insuffisantes".
    """
    return {
        value: [
            str(APPRECIATION_DESCRIPTIONS["followup"][value]),
            str(CONCLUSION_DETAIL[value]),
        ]
        for value in (Appreciation.VERT, Appreciation.JAUNE, Appreciation.ROUGE)
    }


def appreciation_scale(kind):
    """The three levels in order, for the PDF card and the footer legend."""
    return [
        {
            "value": value,
            "label": Appreciation(value).label,
            "description": APPRECIATION_DESCRIPTIONS[kind][value],
        }
        for value in (Appreciation.VERT, Appreciation.JAUNE, Appreciation.ROUGE)
    ]


def appreciation_label(value):
    """Label of an appreciation, or a placeholder when there is no report."""
    if not value:
        return _("Sans rapport")
    return Appreciation(value).label


def email_status_label(template_used):
    return EMAIL_TEMPLATE_LABELS.get(template_used, "")


def email_status_appreciation(template_used):
    return EMAIL_TEMPLATE_APPRECIATION.get(template_used, Appreciation.VERT)


def export_stem(report):
    """The part of an export filename that identifies a report.

    `controle_1234` for the initial report, `suivi2_1234` for the second
    follow-up. Written once and shared by the PDF, the Excel workbook and
    the email attachment: three different names for the same report is
    exactly how a downloads folder becomes unreadable, and the follow-up
    number was missing from all three.
    """
    satac = report.chantier.satac_number
    number = getattr(report, "sequence_number", None)
    return f"suivi{number}_{satac}" if number else f"controle_{satac}"
