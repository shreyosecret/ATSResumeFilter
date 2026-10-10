// Bundle OpenResume's parser (https://github.com/xitanggg/open-resume, AGPL-3.0)
// from a checkout into one CommonJS file that runs under Node. OpenResume's
// source is not modified. Two substitutions make it run outside a browser:
// pdfjs-dist is pointed at its Node ("legacy") build, and the browser worker
// entry is replaced by an empty module (pdfjs then parses on the main thread).
// pdfjs-dist stays a separate package, resolved from node_modules next to the bundle.
import { build } from "esbuild";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

export async function bundle(root, outfile) {
  const lib = path.join(root, "src", "app", "lib");
  const entry = path.join(mkdtempSync(path.join(tmpdir(), "openresume-")), "entry.ts");
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
      b.onResolve({ filter: /^pdfjs-dist$/ }, () => ({ path: "pdfjs-dist/legacy/build/pdf.js", external: true }));
      b.onLoad({ filter: /.*/, namespace: "empty" }, () => ({ contents: "export default undefined;", loader: "js" }));
    },
  };
  await build({
    entryPoints: [entry], bundle: true, platform: "node", format: "cjs", outfile,
    plugins: [redirect], nodePaths: [path.join(here, "node_modules")], logLevel: "error",
  });
  return outfile;
}
