import { readFile } from "node:fs/promises";
import path from "node:path";
import esbuild from "esbuild";

// The published ESM build imports its CSS with `import x from "./y.css" with { type: "css" }`
// (a native "CSS module script" -> CSSStyleSheet), which esbuild's bundler doesn't
// understand out of the box. Reproduce the same shape manually: read the file and
// construct a CSSStyleSheet from it, since that's exactly what the native import
// attribute does in a browser.
const cssModulePlugin = {
  name: "css-module-script",
  setup(build) {
    build.onLoad({ filter: /\.css$/ }, async (args) => {
      const css = await readFile(args.path, "utf8");
      const contents = `
        const sheet = new CSSStyleSheet();
        sheet.replaceSync(${JSON.stringify(css)});
        export default sheet;
      `;
      return { contents, loader: "js" };
    });
  },
};

const MIME_TYPES = {
  ".svg": "image/svg+xml",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
};

// The library's own build (rollup + @rollup/plugin-url, `limit: 0, emitFiles: false`)
// resolves its own image imports to *runtime* `new URL("../img/x.svg", import.meta.url)`
// lookups rather than bundling them, on the assumption the img/ folder sits right next
// to whichever source file referenced it. Once esbuild concatenates every source file
// into one physical output file, all these `import.meta.url` computations collapse to
// that single file's own location, and the "../" counts (which vary per original file's
// nesting depth) resolve to as many as 3 different (wrong) locations. Fix at the source:
// read each referenced asset from disk (relative to the *original* file, still known
// here via args.path) and inline it directly, so nothing is resolved at runtime at all.
const inlineAssetsPlugin = {
  name: "inline-import-meta-assets",
  setup(build) {
    build.onLoad({ filter: /@panoramax[\\/]web-viewer[\\/].*\.js$/ }, async (args) => {
      let contents = await readFile(args.path, "utf8");
      if (!contents.includes("import.meta.url")) {
        return null; // let esbuild's default loader handle it
      }
      const dir = path.dirname(args.path);

      // Pattern 1: `await fetch(new URL("REL", import.meta.url).href).then(res => res.text())`
      // -> inline SVG/text content directly as a string literal.
      const textPattern = /fetch\(new URL\("([^"]+)",\s*import\.meta\.url\)\.href\)\.then\(res\s*=>\s*res\.text\(\)\)/g;
      contents = await replaceAsync(contents, textPattern, async (_match, relPath) => {
        const text = await readFile(path.resolve(dir, relPath), "utf8");
        return JSON.stringify(text);
      });

      // Pattern 2: `new URL("REL", import.meta.url).href` -> inline as a base64 data: URI.
      const urlPattern = /new URL\("([^"]+)",\s*import\.meta\.url\)\.href/g;
      contents = await replaceAsync(contents, urlPattern, async (_match, relPath) => {
        const abs = path.resolve(dir, relPath);
        const buf = await readFile(abs);
        const mime = MIME_TYPES[path.extname(abs).toLowerCase()] || "application/octet-stream";
        return JSON.stringify(`data:${mime};base64,${buf.toString("base64")}`);
      });

      return { contents, loader: "js" };
    });
  },
};

async function replaceAsync(str, regex, asyncFn) {
  const matches = [...str.matchAll(regex)];
  const replacements = await Promise.all(matches.map((m) => asyncFn(...m)));
  let result = "";
  let lastIndex = 0;
  matches.forEach((m, i) => {
    result += str.slice(lastIndex, m.index) + replacements[i];
    lastIndex = m.index + m[0].length;
  });
  result += str.slice(lastIndex);
  return result;
}

await esbuild.build({
  entryPoints: ["node_modules/@panoramax/web-viewer/build/esm/index_photoviewer.js"],
  bundle: true,
  format: "esm",
  minify: true,
  outfile: "../static/panoview/vendor/panoramax-web-viewer.photoviewer.bundle.js",
  plugins: [inlineAssetsPlugin, cssModulePlugin],
});

console.log("Build OK");
