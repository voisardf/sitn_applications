"""
Builds STAC (SpatioTemporal Asset Catalog) representations of the panoramas stored
in the database, for consumption by the Panoramax web viewer.

pystac is used to shape objects that are guaranteed to be spec-compliant, but the
usual pystac object graph (root/parent resolution through in-memory Python objects)
is not used: each request builds a standalone Catalog/Collection/Item and every
link (root, parent, self, collection, prev, next) is set explicitly with a plain
href, computed for the current request.
"""
from django.contrib.gis.db.models import Extent
from django.contrib.gis.db.models.functions import Transform
from django.db.models import Max, Min
from django.urls import reverse

import pystac

from .models import PanoramaItem, Sequence

# The Panoramax viewer was validated against STAC 1.0.0; pystac 1.15 defaults its
# objects to 1.1.0, so the version is forced back after building each dict.
STAC_VERSION = "1.0.0"


def _abs_url(request, url_name, kwargs=None):
    return request.build_absolute_uri(reverse(url_name, kwargs=kwargs))


def catalog_url(request):
    return _abs_url(request, "panoview-catalog")


def _collections_url(request):
    return _abs_url(request, "panoview-collections")


def _collection_url(request, seq_id):
    return _abs_url(request, "panoview-collection", {"seq_id": seq_id})


def _item_url(request, seq_id, item_id):
    return _abs_url(request, "panoview-item", {"seq_id": seq_id, "item_id": item_id})


def _search_url(request):
    return _abs_url(request, "panoview-search")


def _spatial_extent(queryset):
    """2D [minx, miny, maxx, maxy] bbox in WGS84 for the given PanoramaItem queryset."""
    bbox = queryset.annotate(geom_wgs84=Transform("geom", 4326)).aggregate(bbox=Extent("geom_wgs84"))["bbox"]
    return list(bbox) if bbox else None


def _temporal_extent(queryset):
    bounds = queryset.aggregate(min_dt=Min("captured_at"), max_dt=Max("captured_at"))
    return bounds["min_dt"], bounds["max_dt"]


def build_catalog(request):
    title = "SITN Panoramas STAC catalog"
    self_href = catalog_url(request)

    items = PanoramaItem.objects.all()
    bbox = _spatial_extent(items)
    min_dt, max_dt = _temporal_extent(items)

    extra_fields = {}
    if bbox and min_dt and max_dt:
        extra_fields["extent"] = {
            "spatial": {"bbox": [bbox]},
            "temporal": {"interval": [[min_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), max_dt.strftime("%Y-%m-%dT%H:%M:%SZ")]]},
        }

    catalog = pystac.Catalog(
        id="sitn-panoramas",
        description=title,
        title=title,
        extra_fields=extra_fields,
    )
    catalog.set_self_href(self_href)

    # Mandatory per Panoramax viewer, but only used as a href prefix / never fetched
    # directly when both "sequence" and "picture" attributes are set on the viewer.
    catalog.add_link(pystac.Link(rel="data", target=_collections_url(request), media_type="application/json"))
    catalog.add_link(pystac.Link(rel="search", target=_search_url(request), media_type="application/geo+json"))

    for sequence in Sequence.objects.all():
        catalog.add_link(pystac.Link(
            rel="child",
            target=_collection_url(request, sequence.id),
            media_type="application/json",
        ))

    d = catalog.to_dict(include_self_link=True, transform_hrefs=False)
    d["stac_version"] = STAC_VERSION
    return d


def build_collections(request):
    """Best-effort STAC API "GET /collections" listing."""
    return {
        "collections": [build_collection(request, sequence) for sequence in Sequence.objects.all()],
        "links": [
            {"rel": "self", "type": "application/json", "href": _collections_url(request)},
            {"rel": "root", "type": "application/json", "href": catalog_url(request)},
        ],
    }


def build_collection(request, sequence):
    items = PanoramaItem.objects.filter(sequence=sequence)
    bbox = _spatial_extent(items) or [0, 0, 0, 0]
    min_dt, max_dt = _temporal_extent(items)

    extent = pystac.Extent(
        pystac.SpatialExtent([bbox]),
        pystac.TemporalExtent([[min_dt, max_dt]]),
    )

    collection = pystac.Collection(
        id=sequence.id,
        title=sequence.title or sequence.id,
        description=sequence.description or f"SITN mobile-mapping panorama sequence {sequence.site}/{sequence.version}",
        extent=extent,
        license="proprietary",
    )
    collection.set_self_href(_collection_url(request, sequence.id))
    # Replace the root link pystac added automatically (pointing to the collection
    # itself) with one pointing to the actual catalog.
    collection.links = [link for link in collection.links if link.rel != pystac.RelType.ROOT]
    collection.add_link(pystac.Link(rel="root", target=catalog_url(request), media_type="application/json"))
    collection.add_link(pystac.Link(rel="parent", target=catalog_url(request), media_type="application/json"))

    d = collection.to_dict(include_self_link=True, transform_hrefs=False)
    d["stac_version"] = STAC_VERSION
    return d


def _item_properties(item):
    properties = {
        "view:azimuth": item.azimuth,
        "pers:pitch": item.pitch,
        "pers:roll": item.roll,
        "pers:interior_orientation": {"field_of_view": 360},
        # The viewer's PictureMetadata panel unconditionally does
        # Object.entries(properties.exif), crashing if it's missing entirely.
        "exif": {},
        # The semantic-tagging widget unconditionally does properties.semantics.find(...)
        # (SemanticsList._onPicChange -> PresetsManager.getPresets), crashing if it's
        # missing entirely. No semantic tags are managed here, so this just stays empty.
        "semantics": [],
    }
    if item.image_width and item.image_height:
        properties["pers:interior_orientation"]["sensor_array_dimensions"] = [item.image_width, item.image_height]
    return properties


def _wgs84_coords(item):
    """
    WGS84 (lon, lat, alt) for an item's geometry. Reprojection is done PostGIS-side
    (via the "geom_wgs84" annotation, when the queryset that produced `item` set it
    up) rather than client-side GDAL, which depends on a local PROJ data directory
    that isn't guaranteed to be configured on every machine running this code.
    """
    geom_wgs84 = getattr(item, "geom_wgs84", None)
    if geom_wgs84 is None:
        geom_wgs84 = (
            PanoramaItem.objects.filter(pk=item.pk)
            .annotate(geom_wgs84=Transform("geom", 4326))
            .values_list("geom_wgs84", flat=True)
            .get()
        )
    return geom_wgs84.coords


def _neighbor_link(request, rel, neighbor):
    lon, lat, alt = _wgs84_coords(neighbor)
    return pystac.Link(
        rel=rel,
        target=_item_url(request, neighbor.sequence_id, neighbor.id),
        media_type="application/geo+json",
        extra_fields={
            "id": neighbor.id,
            "datetime": neighbor.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "geometry": {"type": "Point", "coordinates": [lon, lat, alt]},
        },
    )


def build_item(request, item):
    lon, lat, alt = _wgs84_coords(item)

    stac_item = pystac.Item(
        id=item.id,
        geometry={"type": "Point", "coordinates": [lon, lat, alt]},
        bbox=[lon, lat, lon, lat],
        datetime=item.captured_at,
        properties=_item_properties(item),
        collection=item.sequence_id,
    )
    stac_item.set_self_href(_item_url(request, item.sequence_id, item.id))
    stac_item.add_asset("image", pystac.Asset(
        href=f"{item.sequence.base_image_url.rstrip('/')}/{item.image_name}",
        media_type="image/jpeg",
        roles=["data", "visual"],
    ))
    stac_item.add_link(pystac.Link(
        rel="collection",
        target=_collection_url(request, item.sequence_id),
        media_type="application/json",
    ))

    neighbors = PanoramaItem.objects.filter(sequence_id=item.sequence_id).annotate(geom_wgs84=Transform("geom", 4326))
    prev_item = neighbors.filter(rank__lt=item.rank).order_by("-rank").first()
    next_item = neighbors.filter(rank__gt=item.rank).order_by("rank").first()
    if prev_item:
        stac_item.add_link(_neighbor_link(request, "prev", prev_item))
    if next_item:
        stac_item.add_link(_neighbor_link(request, "next", next_item))

    d = stac_item.to_dict(include_self_link=True, transform_hrefs=False)
    d["stac_version"] = STAC_VERSION
    return d


def build_search(request, query_params):
    """
    Best-effort STAC search: supports the "ids", "collections", "bbox" and "limit"
    query parameters (as a simple GET, no POST body / paging).
    """
    queryset = PanoramaItem.objects.select_related("sequence").annotate(geom_wgs84=Transform("geom", 4326))

    ids = query_params.get("ids")
    if ids:
        queryset = queryset.filter(id__in=[v for v in ids.split(",") if v])

    collections = query_params.get("collections")
    if collections:
        queryset = queryset.filter(sequence_id__in=[v for v in collections.split(",") if v])

    bbox = query_params.get("bbox")
    if bbox:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(",")[:4])
        queryset = queryset.filter(
            geom_wgs84__bboverlaps=f"POLYGON(({minx} {miny}, {maxx} {miny}, {maxx} {maxy}, {minx} {maxy}, {minx} {miny}))"
        )

    limit = int(query_params.get("limit") or 10000)
    queryset = queryset[:limit]

    return {
        "type": "FeatureCollection",
        "features": [build_item(request, item) for item in queryset],
        "links": [
            {"rel": "self", "type": "application/geo+json", "href": _search_url(request)},
            {"rel": "root", "type": "application/json", "href": catalog_url(request)},
        ],
    }
