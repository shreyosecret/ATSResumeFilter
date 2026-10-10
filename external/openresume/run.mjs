// Run OpenResume's PDF parser (https://github.com/xitanggg/open-resume, AGPL-3.0)
// on local files and print one JSON object per line:
//
//   OPENRESUME_DIR=/path/to/open-resume node run.mjs a.pdf b.pdf
//
// Bundles OpenResume from that checkout (bundle.mjs) next to this folder's
// node_modules, then parses (parse.cjs). The desktop app ships a prebuilt
// bundle instead (prebuild.mjs).
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "./bundle.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = process.env.OPENRESUME_DIR;
if (!root) {
  console.error("Set OPENRESUME_DIR to an open-resume checkout");
  process.exit(2);
}
const out = await bundle(root, path.join(here, ".build", "bundle.cjs"));
const main = createRequire(import.meta.url)("./parse.cjs");
await main(out, process.argv.slice(2));
