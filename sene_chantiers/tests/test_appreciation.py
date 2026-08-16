"""Cascades d'appréciation : les trois règles confirmées."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ..models import (
    Appreciation,
    Conformity,
    FollowUpStatus,
    Theme,
)
from ..services import appreciation
from .factories import (
    TODAY,
    make_control_report,
    seed_sections,
)


class ThemeAppreciationTest(TestCase):
    """0 Non → vert, 1 → jaune, 2+ → rouge ; N.A. ne compte pas."""

    def test_all_compliant(self):
        self.assertEqual(
            appreciation.theme_appreciation([Conformity.YES] * 4), Appreciation.VERT
        )

    def test_single_non_compliance(self):
        self.assertEqual(
            appreciation.theme_appreciation([Conformity.YES, Conformity.NO]),
            Appreciation.JAUNE,
        )

    def test_two_non_compliances(self):
        self.assertEqual(
            appreciation.theme_appreciation([Conformity.NO, Conformity.NO]),
            Appreciation.ROUGE,
        )

    def test_not_applicable_is_not_a_non_compliance(self):
        self.assertEqual(
            appreciation.theme_appreciation(
                [Conformity.YES, Conformity.NOT_APPLICABLE]
            ),
            Appreciation.VERT,
        )

    def test_fully_not_applicable_theme_is_jaune(self):
        """Rien n'a été évalué : ce n'est pas une conformité."""
        self.assertEqual(
            appreciation.theme_appreciation([Conformity.NOT_APPLICABLE] * 3),
            Appreciation.JAUNE,
        )

    def test_unanswered_theme_stays_vert(self):
        self.assertEqual(appreciation.theme_appreciation(["", ""]), Appreciation.VERT)


class GlobalAppreciationTest(TestCase):
    """Compte de thèmes non conformes, pas la sévérité la plus forte."""

    def test_no_bad_theme(self):
        self.assertEqual(
            appreciation.global_appreciation([Appreciation.VERT] * 5),
            Appreciation.VERT,
        )

    def test_single_bad_theme(self):
        self.assertEqual(
            appreciation.global_appreciation(
                [Appreciation.VERT, Appreciation.ROUGE, Appreciation.VERT]
            ),
            Appreciation.JAUNE,
        )

    def test_two_bad_themes(self):
        self.assertEqual(
            appreciation.global_appreciation(
                [Appreciation.JAUNE, Appreciation.JAUNE, Appreciation.VERT]
            ),
            Appreciation.ROUGE,
        )


class FollowUpAppreciationTest(TestCase):
    def test_all_closed(self):
        self.assertEqual(
            appreciation.followup_global_appreciation([FollowUpStatus.CLOSED] * 3),
            Appreciation.VERT,
        )

    def test_one_open(self):
        self.assertEqual(
            appreciation.followup_global_appreciation(
                [FollowUpStatus.CLOSED, FollowUpStatus.OPEN]
            ),
            Appreciation.JAUNE,
        )

    def test_two_open(self):
        self.assertEqual(
            appreciation.followup_global_appreciation(
                [FollowUpStatus.OPEN, FollowUpStatus.OPEN]
            ),
            Appreciation.ROUGE,
        )

    def test_any_not_done_is_rouge(self):
        self.assertEqual(
            appreciation.followup_global_appreciation(
                [FollowUpStatus.CLOSED, FollowUpStatus.NOT_DONE]
            ),
            Appreciation.ROUGE,
        )


class RecomputeTest(TestCase):
    """La recomposition met à jour les thèmes puis rend l'appréciation globale."""

    def setUp(self):
        self.report = make_control_report()
        seed_sections(self.report)

    def test_two_non_compliances_in_one_theme(self):
        theme = Theme.objects.get(code="dechets")
        answers = self.report.control_point_answers.filter(
            control_point__theme=theme
        )
        for answer in answers:
            answer.conformity = Conformity.YES
            answer.save()
        for answer in answers[:2]:
            answer.conformity = Conformity.NO
            answer.save()
        for answer in self.report.control_point_answers.exclude(
            control_point__theme=theme
        ):
            answer.conformity = Conformity.YES
            answer.save()

        suggested = appreciation.recompute_control_report(self.report)

        # Deux Non dans un seul thème : ce thème est rouge, mais un seul
        # thème non conforme laisse le rapport en jaune.
        self.assertEqual(
            self.report.theme_assessments.get(theme=theme).appreciation,
            Appreciation.ROUGE,
        )
        self.assertEqual(suggested, Appreciation.JAUNE)


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------
