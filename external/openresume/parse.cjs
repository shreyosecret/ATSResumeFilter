// Parse resume PDFs with a bundled OpenResume parser and print one JSON object
// per line: node parse.cjs a.pdf b.pdf  (bundle.cjs and node_modules/pdfjs-dist beside it)
const path = require("node:path");

// pdfjs's Node build wants the native "canvas" package for DOMMatrix and Path2D,
// which are only used to render pages; text extraction never touches them.
globalThis.DOMMatrix ??= class DOMMatrix {};
globalThis.Path2D ??= class Path2D {};

async function main(bundlePath, files) {
  const { parseResumeFromPdf } = require(bundlePath);
  for (const file of files) {
    try {
      const resume = await parseResumeFromPdf(path.resolve(file));  // pdfjs under Node reads a path
      console.log(JSON.stringify({ file, resume }));
    } catch (e) {
      console.log(JSON.stringify({ file, error: String((e && e.message) || e) }));
    }
  }
}

module.exports = main;
if (require.main === module) main(path.join(__dirname, "bundle.cjs"), process.argv.slice(2));
