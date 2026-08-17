/* Read-only situation map: WMTS city plan + the geoportal's own permit layer.
 *
 * EPSG:2056 is declared inline rather than through proj4: everything here
 * is already in that projection, so nothing is ever reprojected. This is
 * the same approach django-extended-ol takes in WMTSWidget.js.
 */
(function () {
  'use strict';

  const holder = document.querySelector('[data-situation-map]');
  const configEl = document.getElementById('situation-map-config');
  if (!holder || !configEl || typeof ol === 'undefined') {
    return;
  }
  const cfg = JSON.parse(configEl.textContent);

  const projection = new ol.proj.Projection({
    code: 'EPSG:' + cfg.srid,
    extent: cfg.extent,
    units: 'm'
  });

  // The tile grid comes straight from the configured resolutions, so the
  // background lines up with every other SITN map.
  const tileGrid = new ol.tilegrid.WMTS({
    origin: [cfg.extent[0], cfg.extent[3]],
    resolutions: cfg.resolutions,
    matrixIds: cfg.resolutions.map((_, i) => String(i))
  });

  const background = new ol.layer.Tile({
    source: new ol.source.WMTS({
      url: cfg.wmts.url,
      layer: cfg.wmts.layer,
      style: cfg.wmts.style,
      matrixSet: cfg.wmts.matrixSet,
      format: cfg.wmts.format,
      requestEncoding: cfg.wmts.requestEncoding,
      projection: projection,
      tileGrid: tileGrid,
      attributions: cfg.wmts.attributions || undefined,
      wrapX: false
    })
  });

  const permits = new ol.layer.Image({
    source: new ol.source.ImageWMS({
      url: cfg.wms.url,
      params: Object.assign({ TRANSPARENT: true, FORMAT: 'image/png' },
                            cfg.wms.params),
      projection: projection,
      ratio: 1,
      crossOrigin: 'anonymous'
    })
  });

  const map = new ol.Map({
    target: holder,
    layers: [background, permits],
    controls: ol.control.defaults.defaults({
      attribution: true,
      rotate: false
    }),
    // Read-only: no dragging or drawing, only the zoom buttons. The site
    // stays framed, which is the whole point of a situation map.
    interactions: ol.interaction.defaults.defaults({
      dragPan: false,
      mouseWheelZoom: false,
      doubleClickZoom: false,
      altShiftDragRotate: false,
      pinchRotate: false,
      shiftDragZoom: false
    }),
    view: new ol.View({
      projection: projection,
      center: cfg.center,
      resolution: cfg.resolution,
      resolutions: cfg.resolutions,
      constrainResolution: true
    })
  });

  // The container is sized by CSS aspect-ratio, which OpenLayers cannot
  // know about at construction time.
  window.addEventListener('resize', () => map.updateSize());
  requestAnimationFrame(() => map.updateSize());
})();
