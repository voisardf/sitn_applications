# panoview vendor build

This produces the single self-contained JS file loaded by
`panoview/templates/panoview/panorama.html`:

    panoview/static/panoview/vendor/panoramax-web-viewer.photoviewer.bundle.js

## Why

`@panoramax/web-viewer`'s published ESM build (`build/esm/index_photoviewer.js`)
uses bare module specifiers (`import ... from "lit"`, `"maplibre-gl"`, etc.), so
the browser can't load it directly with a plain `<script type="module" src="...">`
- historically this project resolved them with an `<script type="importmap">`
pointing at jsDelivr. This build step bundles everything (the library and all of
its dependencies) into one local file instead, so the page needs neither a CDN
nor an import map.

The published CJS build (`build/cjs/*`) is not used as a shortcut here: it's
already fully self-contained (see the upstream `rollup.config.js`, `external: []`),
but it's compiled to CommonJS (`format: 'cjs'`), which throws `exports is not
defined` in a plain browser `<script>` for some code paths (observed on the Zoom
widget).

`build.mjs` also has to work around the library's own icon/image imports
(`switch_big.svg`, `logo_dead.svg`, `loader_base.jpg`, ...): the published build
resolves each one to a *runtime* `new URL("../img/x.svg", import.meta.url)`
lookup rather than bundling it, assuming its `img/` folder sits right next to
whichever source file referenced it. Once esbuild concatenates everything into
one file, all those lookups collapse to that single file's location, and since
the original files were nested at different depths, they 404 at several
different (wrong) paths instead. The `inlineAssetsPlugin` in `build.mjs` reads
each referenced asset from disk (while file-level identity - and thus the
correct relative path - is still known) and inlines it directly as a string or
base64 `data:` URI, so nothing is resolved at runtime at all.

## Rebuilding (e.g. after bumping the `@panoramax/web-viewer` version)

Requires Node.js (only for this one-off build step - the Django app itself has
no Node/npm dependency at runtime or in deployment).

```
cd panoview/vendor_build
npm install
npm run build
```

This regenerates `../static/panoview/vendor/panoramax-web-viewer.photoviewer.bundle.js`.
Commit the regenerated bundle.

