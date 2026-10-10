// Build the OpenResume engine the desktop app ships:
//   OPENRESUME_DIR=/path/to/open-resume node prebuild.mjs <out-dir>
// writes <out-dir>/bundle.cjs, parse.cjs and node_modules/pdfjs-dist (its Node build).
import { cpSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "./bundle.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2]);
mkdirSync(out, { recursive: true });
await bundle(process.env.OPENRESUME_DIR, path.join(out, "bundle.cjs"));
cpSync(path.join(here, "parse.cjs"), path.join(out, "parse.cjs"));
const pdfjs = path.join(here, "node_modules", "pdfjs-dist");
const dest = path.join(out, "node_modules", "pdfjs-dist");
cpSync(path.join(pdfjs, "package.json"), path.join(dest, "package.json"));
cpSync(path.join(pdfjs, "LICENSE"), path.join(dest, "LICENSE"));
cpSync(path.join(pdfjs, "legacy", "build"), path.join(dest, "legacy", "build"), { recursive: true });
console.log("OpenResume engine in", out);
