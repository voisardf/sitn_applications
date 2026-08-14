"""Seed the fixed reference data taken from the paper forms.

Themes and control points are the section 02/04 checklist; weather and
construction phases are starting values the admin can extend or rename.
"""

from django.db import migrations

# (code, label, [control points]) — order follows the paper form.
THEMES = [
    (
        "air",
        "Air et poussières",
        [
            "Limitation des poussières",
            "Arrosage si nécessaire",
            "Camions bâchés",
            "Voies d'accès nettoyées",
            "Pas de brûlage de déchets",
            "Machines entretenues",
            "Moteurs coupés à l'arrêt",
        ],
    ),
    (
        "bruit",
        "Bruit et vibrations",
        [
            "Respect des horaires de travail",
            "Limitation des nuisances sonores",
            "Machines adaptées et entretenues",
            "Moteurs coupés à l'arrêt",
            "Mesures de réduction si nécessaire",
        ],
    ),
    (
        "eaux",
        "Eaux",
        [
            "Pas de rejet polluant",
            "Gestion correcte des eaux de chantier",
            "Bassin de décantation si nécessaire",
            "Protection des écoulements",
            "Pas de laitance de béton",
            "Stockage sécurisé des polluants",
        ],
    ),
    (
        "dechets",
        "Déchets",
        [
            "Tri des déchets conforme",
            "Bennes identifiées et adaptées",
            "Déchets séparés par catégorie",
            "Pas de dépôt sauvage",
            "Stockage sécurisé des déchets spéciaux",
            "Évacuation conforme des déchets",
            "Gestion correcte des matériaux d'excavation",
        ],
    ),
    (
        "sols",
        "Sols",
        [
            "Pas de pollution du sol",
            "Produits polluants sur rétention",
            "Tri des terres excavées",
            "Pas de mélange terre/déchets",
            "Stockage des matériaux adapté",
            "Remise en état du site",
        ],
    ),
]

WEATHER_CONDITIONS = ["Ensoleillé", "Nuageux", "Pluie", "Neige", "Vent"]

CONSTRUCTION_PHASES = [
    "Terrassement",
    "Gros œuvre",
    "Réseaux",
    "Second œuvre",
    "Finitions",
    "Aménagements extérieurs",
]


def seed(apps, schema_editor):
    Theme = apps.get_model("sene_chantiers", "Theme")
    ControlPoint = apps.get_model("sene_chantiers", "ControlPoint")
    WeatherCondition = apps.get_model("sene_chantiers", "WeatherCondition")
    ConstructionPhase = apps.get_model("sene_chantiers", "ConstructionPhase")

    for theme_order, (code, label, points) in enumerate(THEMES):
        theme = Theme.objects.create(code=code, label=label, order=theme_order)
        ControlPoint.objects.bulk_create(
            [
                ControlPoint(theme=theme, label=point, order=point_order)
                for point_order, point in enumerate(points)
            ]
        )

    WeatherCondition.objects.bulk_create(
        [
            WeatherCondition(label=label, order=order)
            for order, label in enumerate(WEATHER_CONDITIONS)
        ]
    )
    ConstructionPhase.objects.bulk_create(
        [
            ConstructionPhase(label=label, order=order)
            for order, label in enumerate(CONSTRUCTION_PHASES)
        ]
    )


class Migration(migrations.Migration):
    dependencies = [("sene_chantiers", "0001_initial")]
    # No reverse: reports reference these rows with PROTECT, so deleting
    # them would either fail or require destroying report data. Reversing
    # 0001 drops the tables outright, which is the real undo.
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
