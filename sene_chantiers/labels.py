"""Display labels for the traffic-light states.

Two vocabularies deliberately coexist, as drawn in the mockups: the
dossier/report pill describes the state of the site, while the Courriels
column describes what the email asks the recipient to do.
"""

from django.utils.translation import gettext_lazy as _

from .models import Appreciation, EmailTemplate

# Dossier and report level — describes the finding.
APPRECIATION_LABELS = {
    Appreciation.VERT: _("Conforme"),
    Appreciation.JAUNE: _("Écarts mineurs"),
    Appreciation.ROUGE: _("Non conforme"),
}

# Courriels list — describes the action requested.
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


def appreciation_label(value):
    return APPRECIATION_LABELS.get(value, _("Sans rapport"))


def email_status_label(template_used):
    return EMAIL_TEMPLATE_LABELS.get(template_used, "")


def email_status_appreciation(template_used):
    return EMAIL_TEMPLATE_APPRECIATION.get(template_used, Appreciation.VERT)
