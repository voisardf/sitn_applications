"""Appreciation cascades.

Pure functions so the rules can be exercised directly. Each result is a
suggestion: the inspector can always override it, and an override is
remembered through `global_appreciation_is_manual_override`.

Rules (confirmed 2026-08-13):
  Per theme, from its section 04 checklist:
      0 "Non"                      -> Vert
      exactly 1 "Non"              -> Jaune
      2 or more "Non"              -> Rouge
      every point N.A.             -> Jaune
  Report-wide, from the count of non-compliant themes:
      0 non-compliant themes       -> Vert
      exactly 1                    -> Jaune
      2 or more                    -> Rouge
  Follow-up report, from the measure statuses:
      0 still open / not done      -> Vert
      exactly 1 still open         -> Jaune
      any not done, or 2+ open     -> Rouge
"""

from ..models import Appreciation, Conformity, FollowUpStatus


def theme_appreciation(conformities):
    """Appreciation for one theme, from its checklist answers."""
    answers = [c for c in conformities if c]
    if not answers:
        return Appreciation.VERT

    if all(c == Conformity.NOT_APPLICABLE for c in answers):
        # Nothing was actually assessed for this theme.
        return Appreciation.JAUNE

    non_compliant = sum(1 for c in answers if c == Conformity.NO)
    if non_compliant == 0:
        return Appreciation.VERT
    if non_compliant == 1:
        return Appreciation.JAUNE
    return Appreciation.ROUGE


def global_appreciation(theme_appreciations):
    """Report-wide appreciation, counting non-compliant themes."""
    non_compliant = sum(1 for a in theme_appreciations if a != Appreciation.VERT)
    if non_compliant == 0:
        return Appreciation.VERT
    if non_compliant == 1:
        return Appreciation.JAUNE
    return Appreciation.ROUGE


def followup_global_appreciation(statuses):
    """Follow-up appreciation, from the state of the re-checked measures."""
    open_count = sum(1 for s in statuses if s == FollowUpStatus.OPEN)
    not_done = any(s == FollowUpStatus.NOT_DONE for s in statuses)

    if not_done or open_count >= 2:
        return Appreciation.ROUGE
    if open_count == 1:
        return Appreciation.JAUNE
    return Appreciation.VERT


def recompute_control_report(control_report):
    """Refresh every theme appreciation, then the report's own.

    Returns the suggested global appreciation without saving it, so the
    caller decides whether a manual override wins.
    """
    theme_values = []
    answers_by_theme = {}
    for answer in control_report.control_point_answers.select_related(
        "control_point"
    ):
        answers_by_theme.setdefault(answer.control_point.theme_id, []).append(
            answer.conformity
        )

    for assessment in control_report.theme_assessments.all():
        value = theme_appreciation(answers_by_theme.get(assessment.theme_id, []))
        if assessment.appreciation != value:
            assessment.appreciation = value
            assessment.save(update_fields=["appreciation"])
        theme_values.append(value)

    return global_appreciation(theme_values)
