"""Fabriques et chargement des données de référence pour les tests.

Les tables partagées (`Commune`, `SearchSatac`,
`At034AutorisationConstruire`) sont `managed = False` : Django ne les crée
pas. Leur présence dépend de ce que `manage.py testdb` a cloné depuis la
base locale.

Plutôt que de tout simuler, on insère de vraies lignes fictives dans
celles qui existent, et on saute proprement les tests qui dépendent d'une
table absente — avec un message qui dit quoi faire. Un test qui passerait
en silence sans avoir rien vérifié serait pire qu'un test sauté.
"""

import io
import json
import unittest
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.contrib.gis.geos import Point
from django.db import connection
from django.utils import timezone
from PIL import Image

from cadastre.models import Commune

from ..models import (
    At034AutorisationConstruire,
    Chantier,
    ConstructionPhase,
    ControlPoint,
    ControlPointAnswer,
    ControlReport,
    CorrectiveMeasure,
    CorrectiveMeasureReport,
    MeasureStatus,
    SearchSatac,
    Theme,
    ThemeAssessment,
    WeatherCondition,
)

TODAY = timezone.localdate()
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SRID = 2056


def load_reference_data():
    """Read the fictitious reference rows shipped with the tests."""
    with open(FIXTURES / "satac_reference.json", encoding="utf-8") as handle:
        return json.load(handle)


def _point(geometry):
    """GeoJSON implies WGS84; these coordinates are MN95, so build directly."""
    x, y = geometry["coordinates"]
    return Point(x, y, srid=SRID)


def table_exists(model):
    """True when the unmanaged table backing a model is present."""
    table = model._meta.db_table.replace('"."', ".")
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [table])
        return cursor.fetchone()[0] is not None


def require_table(model, hint):
    if not table_exists(model):
        raise unittest.SkipTest(
            f"{model._meta.db_table} absente de la base de test — {hint}"
        )


def seed_search_satac():
    """Insert the fictitious locator rows."""
    require_table(
        SearchSatac,
        "relancer manage.py testdb pour recloner le schéma searchtables",
    )
    data = load_reference_data()["search_satac"]
    created = []
    for row in data:
        created.append(
            SearchSatac.objects.create(
                idobj=row["idobj"],
                instance_id=row["instance_id"],
                state_code=row["state_code"] or "",
                search_satac=row["search_satac"],
                geom=_point(row["geometry"]),
                actions=row["actions"],
            )
        )
    return created


def seed_at034():
    """Insert the fictitious permit rows.

    The amenagement schema is only present once it has been cloned into
    the test database; tests needing it are skipped otherwise.
    """
    require_table(
        At034AutorisationConstruire,
        "charger le schéma amenagement en local puis relancer manage.py testdb",
    )
    created = []
    for row in load_reference_data()["at034"]:
        if row.get("_comment"):
            row = {k: v for k, v in row.items() if k != "_comment"}
        created.append(
            At034AutorisationConstruire.objects.create(
                idobj=row["idobj"],
                instance_id=row["instance_id"],
                commune=row["commune"],
                idcom=row["idcom"],
                geom=_point(row["geometry"]),
                description_ouvrage=row["description_ouvrage"],
                requerant=row["requerant"],
                etat_dossier=row["etat_dossier"],
                parcelle=row["parcelle"],
                zone=row["zone"],
            )
        )
    return created


def a_commune():
    """A real commune from the shared reference table."""
    commune = Commune.objects.first()
    if commune is None:
        raise unittest.SkipTest(
            "general.la3_limites_communales est vide — lancer manage.py testdb"
        )
    return commune


# ---------------------------------------------------------------------------
# Fabriques
# ---------------------------------------------------------------------------


def make_user(username="inspecteur", in_group=True, **kwargs):
    user = User.objects.create_user(
        username=username, password="x", email=f"{username}@example.ch", **kwargs
    )
    if in_group:
        group, _ = Group.objects.get_or_create(name="sene_chantiers_admin")
        user.groups.add(group)
    return user


def make_chantier(satac_number=999001, **kwargs):
    defaults = {
        "site_name": "Réaménagement du secteur des Tilleuls",
        "adresse": "Rue des Tilleuls 12",
        "commune": a_commune(),
        "maitre_ouvrage": "Commune exemple",
        "maitre_ouvrage_email": "exemple@example.ch",
        "entreprise_generale": "Entreprise exemple SA",
    }
    defaults.update(kwargs)
    return Chantier.objects.create(satac_number=satac_number, **defaults)


def make_control_report(chantier=None, user=None, **kwargs):
    chantier = chantier or make_chantier()
    defaults = {
        "control_date": TODAY,
        "weather_condition": WeatherCondition.objects.first(),
        "construction_phase": ConstructionPhase.objects.first(),
        "inspector": user or make_user(f"insp{chantier.satac_number}"),
    }
    defaults.update(kwargs)
    return ControlReport.objects.create(chantier=chantier, **defaults)


def seed_sections(report):
    """The fixed section 02 and 04 rows, as the create view materialises them."""
    ThemeAssessment.objects.bulk_create(
        [ThemeAssessment(control_report=report, theme=t) for t in Theme.objects.all()]
    )
    ControlPointAnswer.objects.bulk_create(
        [
            ControlPointAnswer(control_report=report, control_point=p, conformity="")
            for p in ControlPoint.objects.all()
        ]
    )


def make_measure(report, order=1, **kwargs):
    defaults = {
        "description": "Corriger le tri des déchets",
        "responsible": "Entreprise exemple SA",
        "deadline": TODAY + timedelta(days=30),
        "status": MeasureStatus.OPEN,
    }
    defaults.update(kwargs)
    return CorrectiveMeasure.objects.create(
        control_report=report, order=order, **defaults
    )


def make_followup(chantier, user=None, **kwargs):
    defaults = {
        "follow_up_date": TODAY,
        "inspector": user or make_user(f"suivi{chantier.satac_number}"),
    }
    defaults.update(kwargs)
    return CorrectiveMeasureReport.objects.create(chantier=chantier, **defaults)


def jpeg_bytes(width=320, height=240, **save_kwargs):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (80, 130, 90)).save(
        buffer, "JPEG", **save_kwargs
    )
    return buffer.getvalue()
