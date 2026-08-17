"""Configuration for the situation map.

The map is read-only: it shows where a permit is, and is never used to
capture a geometry — `Chantier.geom` comes from the SATAC lookup alone.
That is why this is a plain OpenLayers map rather than the
`WMTSWithSearchWidget` used by `ppe`: that widget is a *form* widget, it
always wires Draw and Modify interactions plus a serialized textarea, and
the shipped OLMapWidget.js has no read-only mode.

What it does reuse is the monorepo's existing map configuration
(`settings.OLWIDGET`): same projection, extent, resolutions and tile
service as every other map in `sitn_applications`. Only the background
layer differs — `plan_ville` rather than the global default
`plan_cadastral` — so nothing here changes maps in the other apps.
"""

from django.conf import settings

# Background: the city plan, as asked for. Overridden per map rather than
# in settings, so the other apps keep their own default.
BACKGROUND_LAYER = "plan_ville"

# The building permits, taken from the geoportal's own published layer so
# the symbol is identical to the one staff see there (a blue pin carrying
# the SATAC number). Drawing it ourselves would mean maintaining a second
# copy of a symbology we do not own.
PERMITS_WMS_URL = "https://sitn.ne.ch/services/wms"
PERMITS_WMS_MAP = "services"
PERMITS_WMS_LAYER = "at034_autorisation_construire_apres"
# The layer carries a time dimension; without it the server returns the
# full history and the view fills with expired permits.
PERMITS_WMS_TIME = "2024-01-01/2028-01-01"

# Roughly 1:2000 — close enough to read the streets around the site
# without losing the neighbourhood.
SITE_RESOLUTION = 0.5


def situation_map_config(geom):
    """Everything the browser needs to draw one situation map."""
    globals_ = settings.OLWIDGET["globals"]
    wmts = settings.OLWIDGET["wmts"]
    return {
        "srid": globals_["srid"],
        "extent": globals_["extent"],
        "resolutions": globals_["resolutions"],
        "center": [geom.x, geom.y],
        "resolution": SITE_RESOLUTION,
        "wmts": {
            "url": wmts["url_template"],
            "layer": BACKGROUND_LAYER,
            "style": wmts["style"],
            "matrixSet": wmts["matrix_set"],
            "format": wmts.get("format", "image/png"),
            "requestEncoding": wmts.get("request_encoding", "KVP"),
            "attributions": wmts.get("attributions"),
        },
        "wms": {
            "url": PERMITS_WMS_URL,
            "params": {
                "MAP": PERMITS_WMS_MAP,
                "LAYERS": PERMITS_WMS_LAYER,
                "TIME": PERMITS_WMS_TIME,
            },
        },
    }
