from django.conf import settings
from django.contrib.gis.db.models.functions import Distance, Transform
from django.contrib.gis.geos import Point
from django.db.models.functions import ExtractYear
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from . import stac
from .models import PanoramaItem, Sequence

ROADVIEW_MAX_DISTANCE_M = 20


def _json(data):
    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


def catalog_view(request):
    return _json(stac.build_catalog(request))


def configuration_view(request):
    """
    The viewer always probes "{endpoint}/configuration" for auth capabilities
    (see @panoramax/web-viewer's API.getAuthURL()), even though our STAC endpoint
    is a static catalog.json with no such concept. There is no auth here, so an
    empty object is a valid "no capabilities" response.
    """
    return _json({})


def collections_view(request):
    return _json(stac.build_collections(request))


def collection_view(request, seq_id):
    sequence = get_object_or_404(Sequence, pk=seq_id)
    return _json(stac.build_collection(request, sequence))


def item_view(request, seq_id, item_id):
    queryset = PanoramaItem.objects.select_related("sequence").annotate(geom_wgs84=Transform("geom", 4326))
    item = get_object_or_404(queryset, pk=item_id, sequence_id=seq_id)
    return _json(stac.build_item(request, item))


def search_view(request):
    try:
        return _json(stac.build_search(request, request.GET))
    except ValueError:
        return HttpResponseBadRequest("Invalid query parameters")


def panorama_view(request, item_id):
    """Serves the streetview-style HTML page for a given picture id."""
    item = get_object_or_404(PanoramaItem, pk=item_id)
    return render(request, "panoview/panorama.html", {
        "picture_id": item.id,
        "sequence_id": item.sequence_id,
        "stac_endpoint": stac.catalog_url(request),
    })


def panoview_base_view(request):
    """
    Redirects to the most recent and closest picture to the given coordinates, provided it's
    within ROADVIEW_MAX_DISTANCE_M meters.
    """
    try:
        east = float(request.GET["east"])
        north = float(request.GET["north"])
    except KeyError:
        return HttpResponseBadRequest('Parameters "east" and "north" are required')
    except ValueError:
        return HttpResponseBadRequest('Parameters "east" and "north" are not numbers')

    point = Point(east, north, srid=settings.DEFAULT_SRID)

    years = (
        PanoramaItem.objects
        .annotate(captured_year=ExtractYear("captured_at"))
        .order_by("-captured_year")
        .values_list("captured_year", flat=True)
        .distinct()
    )

    closest = None
    for year in years:
        candidate = (
            PanoramaItem.objects
            .filter(captured_at__year=year)
            .annotate(distance=Distance("geom", point))
            .order_by("distance")
            .first()
        )
        if candidate is not None and candidate.distance.m <= ROADVIEW_MAX_DISTANCE_M:
            closest = candidate
            break

    if closest is None:
        return render(request, "panoview/panorama_not_found.html", {"max_distance": ROADVIEW_MAX_DISTANCE_M})

    redirect_url = reverse("panoview-panorama", kwargs={"item_id": closest.id})
    return HttpResponseRedirect(f"{redirect_url}?x=-1&z=0")
