"""Drive the application the way an inspector does, through the pages.

Every payload here is scraped from the **rendered form** and posted back,
exactly as a browser would. That matters: the tests that built payloads by
hand from the ORM could not see that the control report was missing a
required field in its template, so they passed while the form was
impossible to save. Anything a person fills in should be exercised this
way.

The method names are also the vocabulary of the manual walkthrough in
`doc/bookstack/10_scenarios_de_test.md`, so the automated scenarios and
the human ones stay in step.
"""
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from ..models import (
    Conformity,
    CorrectiveMeasureReport,
    FollowUpStatus,
    MeasureStatus,
)

INPUT_RE = re.compile(r'<input[^>]*name="([^"]+)"[^>]*>')
SELECT_RE = re.compile(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', re.S)
TEXTAREA_RE = re.compile(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', re.S)
VALUE_RE = re.compile(r'value="([^"]*)"')
SELECTED_RE = re.compile(r'<option value="([^"]*)"[^>]*selected')
FIRST_OPTION_RE = re.compile(r'<option value="([^"]+)"')


class FormPage:
    """One rendered form, with its fields readable and writable."""

    def __init__(self, client, url):
        self.client = client
        self.url = url
        self.reload()

    def reload(self):
        response = self.client.get(self.url)
        assert response.status_code == 200, f"{self.url} -> {response.status_code}"
        self.html = response.content.decode()
        self.data = self._scrape(self.html)
        return self

    @staticmethod
    def _scrape(html):
        """Every field the page offers, with its current value."""
        data = {}
        for match in INPUT_RE.finditer(html):
            tag, name = match.group(0), match.group(1)
            if 'type="radio"' in tag or 'type="checkbox"' in tag:
                if "checked" in tag:
                    found = VALUE_RE.search(tag)
                    data[name] = found.group(1) if found else "on"
                else:
                    data.setdefault(name, "")
                continue
            found = VALUE_RE.search(tag)
            data[name] = found.group(1) if found else ""
        for match in SELECT_RE.finditer(html):
            name, body = match.group(1), match.group(2)
            chosen = SELECTED_RE.search(body) or FIRST_OPTION_RE.search(body)
            data[name] = chosen.group(1) if chosen else ""
        for match in TEXTAREA_RE.finditer(html):
            data[match.group(1)] = match.group(2).strip()
        return data

    # ---------------------------------------------------------- filling
    def set(self, name, value):
        assert name in self.data, f"{name} is not a field of this page"
        self.data[name] = value
        return self

    def set_all(self, suffix, value):
        """Fill every field whose name ends with `suffix`."""
        for key in [k for k in self.data if k.endswith(suffix)]:
            self.data[key] = value
        return self

    def fields_ending(self, suffix):
        return sorted(k for k in self.data if k.endswith(suffix))

    # ------------------------------------------------------- submitting
    def save(self):
        """Press "Enregistrer"."""
        return self.client.post(self.url, self.data)

    def save_draft(self):
        """Press "Enregistrer le brouillon": incompleteness is allowed."""
        payload = dict(self.data)
        payload["save_draft"] = "1"
        return self.client.post(self.url, payload)


class Inspector:
    """An authenticated SENE inspector working through the interface."""

    def __init__(self, username="inspecteur_sim"):
        User = get_user_model()
        self.user, _ = User.objects.get_or_create(username=username)
        group, _ = Group.objects.get_or_create(
            name=settings.SENE_CHANTIERS_ADMIN_GROUP)
        self.user.groups.add(group)
        self.client = Client()
        self.client.force_login(self.user)

    # ---------------------------------------------------------- dossier
    def open_control_report(self, satac_number):
        """Create the initial report if needed, then open its form."""
        self.client.post(reverse(
            "sene_chantiers:control_report_create", args=[satac_number]))
        return FormPage(self.client, reverse(
            "sene_chantiers:control_report_edit", args=[satac_number]))

    def open_followup(self, satac_number):
        """Open the next follow-up, creating it first."""
        self.client.post(reverse(
            "sene_chantiers:corrective_measure_report_create",
            args=[satac_number]))
        report = (CorrectiveMeasureReport.objects
                  .filter(chantier__satac_number=satac_number)
                  .order_by("-pk").first())
        assert report is not None, "no follow-up was created"
        return FormPage(self.client, reverse(
            "sene_chantiers:corrective_measure_report_edit", args=[report.pk]))

    def landing(self, satac_number):
        return self.client.get(reverse(
            "sene_chantiers:chantier_landing", args=[satac_number]))

    # ------------------------------------------ filling a control report
    def fill_control_report(self, page, non_compliant_points=0, measures=0,
                            deadline=None):
        """Answer the checklist and write the mandatory observations.

        `non_compliant_points` answers that many points "Non", which is
        what drives the appreciation cascade.
        """
        for index, name in enumerate(page.fields_ending("-conformity")):
            page.set(name, Conformity.NO if index < non_compliant_points
                     else Conformity.YES)
        page.set_all("-synthesis_remarks", "Constat de thème")
        page.set_all("-detail_observations", "Observations du thème")
        page.set("observations_generales", "Observations générales")
        page.set("procedure_controle", "Visite de terrain")

        if measures:
            page.set("measures-TOTAL_FORMS", str(measures))
            for index in range(measures):
                page.data.setdefault(f"measures-{index}-id", "")
                page.data[f"measures-{index}-order"] = str(index + 1)
                page.data[f"measures-{index}-description"] = (
                    f"Mesure corrective {index + 1}")
                page.data[f"measures-{index}-responsible"] = "Entreprise"
                page.data[f"measures-{index}-deadline"] = str(deadline)
                page.data[f"measures-{index}-status"] = MeasureStatus.OPEN
            page.set("next_control_date", str(deadline))
        return page

    # ----------------------------------------------- filling a follow-up
    def fill_followup(self, page, statuses, next_control_date=None,
                      escalate=False, closure_state=None):
        """`statuses` is one FollowUpStatus per measure, in table order."""
        rows = page.fields_ending("-status")
        assert len(rows) == len(statuses), (
            f"{len(rows)} measures on the page, {len(statuses)} statuses given")
        for name, status in zip(rows, statuses):
            page.set(name, status)
            prefix = name.rsplit("-", 1)[0]
            page.data[f"{prefix}-findings"] = "Constat de suivi"
            if status != FollowUpStatus.CLOSED and next_control_date:
                page.data[f"{prefix}-new_deadline"] = str(next_control_date)
        if "new_anomalies_description" in page.data:
            page.set("new_anomalies_description", "")
        if next_control_date and "next_control_date" in page.data:
            page.set("next_control_date", str(next_control_date))
        if escalate:
            page.set("is_denunciation_escalation", "on")
        if closure_state:
            page.set("final_closure_state", closure_state)
        return page

    # ------------------------------------------------------------ email
    def send_email(self, kind, report_pk):
        """Send the notification, which locks the report."""
        url = reverse("sene_chantiers:email_manager", args=[kind, report_pk])
        opened = self.client.get(url)
        assert opened.status_code == 200, f"email manager -> {opened.status_code}"
        page = FormPage(self.client, url)
        payload = dict(page.data)
        payload["action"] = "send"
        return self.client.post(url, payload)
