// Run OpenResume's PDF parser (https://github.com/xitanggg/open-resume, AGPL-3.0)
// on local files and print one JSON object per line.
//
//   OPENRESUME_DIR=/path/to/open-resume node run.mjs a.pdf b.pdf
//
// OpenResume's own source is bundled at run time from that checkout and is not
// modified. Two substitutions make it run under Node instead of a browser:
// pdfjs-dist is pointed at its Node ("legacy") build, and the browser worker
// entry is replaced by an empty module (pdfjs then parses on the main thread).
import { build } from "esbuild";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = process.env.OPENRESUME_DIR;
if (!root) {
  console.error("Set OPENRESUME_DIR to an open-resume checkout");
  process.exit(2);
}
const lib = path.join(root, "src", "app", "lib");
const nm = path.join(here, "node_modules");
const out = mkdtempSync(path.join(tmpdir(), "openresume-"));
const entry = path.join(out, "entry.ts");
writeFileSync(entry, `export { parseResumeFromPdf } from "lib/parse-resume-from-pdf";\n`);

const redirect = {
  name: "openresume-node",
  setup(b) {
    b.onResolve({ filter: /^lib\// }, (a) => {
      const base = path.join(lib, a.path.slice(4));
      for (const ext of [".ts", ".tsx", "/index.ts"]) {
        try { readFileSync(base + ext); return { path: base + ext }; } catch {}
      }
      return { path: base };
    });
    b.onResolve({ filter: /^pdfjs-dist\/build\/pdf\.worker\.entry$/ }, () => ({ path: "worker", namespace: "empty" }));
    b.onResolve({ filter: /^pdfjs-dist$/ }, () => ({ path: path.join(nm, "pdfjs-dist", "legacy", "build", "pdf.js"), external: true }));
    b.onLoad({ filter: /.*/, namespace: "empty" }, () => ({ contents: "export default undefined;", loader: "js" }));
  },
};

await build({
  entryPoints: [entry], bundle: true, platform: "node", format: "cjs", outfile: path.join(out, "bundle.cjs"),
  plugins: [redirect], nodePaths: [nm], logLevel: "error",
});
// pdfjs's Node build requires the native "canvas" package for DOMMatrix and
// Path2D, which are only used to render pages. Text extraction never touches
// them, so inert stand-ins avoid the native dependency.
globalThis.DOMMatrix ??= class DOMMatrix {};
globalThis.Path2D ??= class Path2D {};
const { createRequire } = await import("node:module");
const { parseResumeFromPdf } = createRequire(import.meta.url)(path.join(out, "bundle.cjs"));

for (const file of process.argv.slice(2)) {
  try {
    // pdfjs under Node reads a plain filesystem path.
    const resume = await parseResumeFromPdf(path.resolve(file));
    console.log(JSON.stringify({ file, resume }));
  } catch (e) {
    console.log(JSON.stringify({ file, error: String(e && e.message || e) }));
  }
}
