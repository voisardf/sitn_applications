"""SATAC permit lookup.

Resolution order, per the functional specification:
  1. SearchSatac (direct DB) to locate the permit and get its geometry.
  2. At034AutorisationConstruire (direct DB) for the commune.
  3. HTTP fallback on the public SITN full-text endpoint if the local
     tables are unavailable.
Manual entry remains possible for everything this cannot resolve;
site_name, adresse, maitre_ouvrage and entreprise_generale are never
derived here — they are always typed by the inspector.
"""

import logging
from dataclasses import dataclass, field

import requests
from django.db import DatabaseError

from cadastre.models import Commune

from ..models import At034AutorisationConstruire, SearchSatac

logger = logging.getLogger(__name__)

FTS_URL = "https://sitn.ne.ch/search"
FTS_TIMEOUT = 10


@dataclass
class SatacResult:
    """What a lookup can tell us about one permit."""

    satac_number: int
    label: str = ""
    geom: object = None
    commune: Commune | None = None
    commune_name: str = ""
    source: str = "db"
    warnings: list[str] = field(default_factory=list)


def _commune_from_idcom(idcom):
    """at034.idcom matches Commune.numcom (not its primary key)."""
    if idcom is None:
        return None
    return Commune.objects.filter(numcom=idcom).only(
        "idobj", "comnom", "numcom"
    ).first()


def search(term, limit=10):
    """Autocomplete over SATAC numbers. Returns a list of SatacResult."""
    term = (term or "").strip()
    if not term:
        return []

    try:
        qs = SearchSatac.objects.only("instance_id", "search_satac", "geom")
        if term.isdigit():
            qs = qs.filter(instance_id__startswith=term) if len(term) < 6 \
                else qs.filter(instance_id=int(term))
        else:
            qs = qs.filter(search_satac__icontains=term)
        results = [
            SatacResult(
                satac_number=row.instance_id,
                label=row.search_satac,
                geom=row.geom,
            )
            for row in qs.order_by("instance_id")[:limit]
        ]
        if results:
            return results
    except DatabaseError:
        logger.warning("SearchSatac unavailable, falling back to HTTP", exc_info=True)

    return _search_http(term, limit)


def _search_http(term, limit):
    """Public SITN full-text endpoint; used when the local table is empty."""
    try:
        response = requests.get(
            FTS_URL,
            params={"query": term, "limit": limit, "categories": "search_satac"},
            timeout=FTS_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("SATAC full-text lookup failed", exc_info=True)
        return []

    results = []
    for feature in payload.get("features", [])[:limit]:
        label = feature.get("properties", {}).get("label", "")
        digits = "".join(c for c in label if c.isdigit())
        if not digits:
            continue
        results.append(
            SatacResult(
                satac_number=int(digits),
                label=label,
                source="http",
            )
        )
    return results


def resolve(satac_number):
    """Full detail for one SATAC number, or None if nothing matches."""
    try:
        satac_number = int(satac_number)
    except (TypeError, ValueError):
        return None

    result = SatacResult(satac_number=satac_number)

    locator = (
        SearchSatac.objects.only("instance_id", "search_satac", "geom")
        .filter(instance_id=satac_number)
        .first()
    )
    if locator:
        result.label = locator.search_satac
        result.geom = locator.geom
    else:
        result.warnings.append(
            "Numéro SATAC introuvable dans l'index de recherche."
        )

    permit = (
        At034AutorisationConstruire.objects.only(
            "instance_id", "commune", "idcom", "geom"
        )
        .filter(instance_id=satac_number)
        .first()
    )
    if permit:
        result.commune_name = permit.commune or ""
        result.commune = _commune_from_idcom(permit.idcom)
        if result.geom is None:
            result.geom = permit.geom
        if result.commune is None and permit.idcom is not None:
            result.warnings.append(
                f"Commune n° {permit.idcom} absente de la table des communes."
            )
    else:
        result.warnings.append(
            "Aucune autorisation de construire trouvée pour ce numéro SATAC."
        )

    if not locator and not permit:
        return None
    return result
