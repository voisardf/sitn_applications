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
