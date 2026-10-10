"""Build the comparison engines the desktop app ships beside itself.

    python scripts/build_engines.py --out build/engines

writes:

  node[.exe]                      the Node.js runtime that runs OpenResume
  openresume/                     OpenResume's parser bundled for Node (AGPL-3.0)
  pyresparser/pyresparser-runner  pyresparser frozen with Python 3.8 and spaCy 2 (GPL-3.0)
  nltk_data/                      the NLTK corpora pyresparser reads
  LICENSES/, THIRD_PARTY.md       their licenses and where their source is

Both run as separate programs called by the app (ats_sim/engines.py), never
linked into it. OpenResume is cloned at a pinned commit; pyresparser is
installed from PyPI into a Python 3.8 environment made with uv. Either part
can be skipped (--skip-openresume, --skip-pyresparser), and a part that
fails to build is reported and left out, so one platform's missing wheel
does not stop the rest.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENRESUME_REPO = "https://github.com/xitanggg/open-resume"
OPENRESUME_COMMIT = "4f8255a2c763479837f69f1dccf2a3338730cd79"
PYRESPARSER = ["spacy==2.3.9", "pyresparser==1.0.6", "nltk==3.8.1",
               "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-2.3.1/en_core_web_sm-2.3.1.tar.gz",
               "pyinstaller==6.10.0"]
NLTK_DATA = ["stopwords", "words", "punkt", "averaged_perceptron_tagger"]
LICENSE_URLS = {
    "open-resume-AGPL-3.0.txt": f"https://raw.githubusercontent.com/xitanggg/open-resume/{OPENRESUME_COMMIT}/LICENSE",
    "pyresparser-GPL-3.0.txt": "https://raw.githubusercontent.com/OmkarPathak/pyresparser/master/LICENSE",
    "nodejs-LICENSE.txt": "https://raw.githubusercontent.com/nodejs/node/main/LICENSE",
    "spacy-MIT.txt": "https://raw.githubusercontent.com/explosion/spaCy/v2.3.9/LICENSE",
}
EXE = ".exe" if os.name == "nt" else ""


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def build_openresume(out: Path, work: Path) -> None:
    src = Path(os.environ.get("OPENRESUME_DIR") or work / "open-resume")
    if not (src / "src").exists():
        run(["git", "clone", "-q", OPENRESUME_REPO, src])
        run(["git", "-C", src, "checkout", "-q", OPENRESUME_COMMIT])
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    run([npm, "ci", "--no-audit", "--no-fund", "--ignore-scripts"], cwd=ROOT / "external" / "openresume")
    # esbuild ships its binary through an optional dependency, not an install script
    run(["node", ROOT / "external" / "openresume" / "prebuild.mjs", out / "openresume"],
        env=dict(os.environ, OPENRESUME_DIR=str(src)))
    shutil.copy2(shutil.which("node"), out / f"node{EXE}")
    probe = subprocess.run([out / f"node{EXE}", out / "openresume" / "parse.cjs",
                            ROOT / "data" / "smoke" / "smoke.pdf"], capture_output=True, text=True)
    if '"resume"' not in probe.stdout:
        raise RuntimeError(f"OpenResume engine does not run: {probe.stdout[-500:]} {probe.stderr[-1500:]}")


def build_pyresparser(out: Path, work: Path) -> None:
    env_dir = work / "pyresparser-env"
    uv = shutil.which("uv")
    run([uv, "python", "install", "3.8"])
    if not env_dir.exists():
        run([uv, "venv", "-q", "-p", "3.8", env_dir])
    py = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([uv, "pip", "install", "-q", "--python", py, *PYRESPARSER])
    nltk_dir = out / "nltk_data"
    run([py, "-m", "nltk.downloader", "-q", "-d", nltk_dir, *NLTK_DATA])
    for z in nltk_dir.glob("*/*.zip"):  # each corpus arrives zipped and unzipped; NLTK reads either
        if z.with_suffix("").is_dir():
            z.unlink()
    for pickle in nltk_dir.glob("tokenizers/punkt/**/*.pickle"):  # pyresparser reads English only
        if pickle.stem != "english":
            pickle.unlink()
    dist, build = work / "pyi-dist", work / "pyi-build"
    collect = ["spacy", "thinc", "srsly", "blis", "cymem", "preshed", "murmurhash", "wasabi", "catalogue",
               "en_core_web_sm", "pyresparser", "nltk", "pdfminer", "docx2txt"]
    run([py, "-m", "PyInstaller", "--noconfirm", "--onedir", "--name", "pyresparser-runner",
         "--distpath", dist, "--workpath", build, "--specpath", work,
         *[a for c in collect for a in ("--collect-all", c)],
         *[a for m in ("tkinter", "_tkinter", "matplotlib", "IPython", "PyQt5", "PySide2")
           for a in ("--exclude-module", m)],  # NLTK imports a GUI toolkit it never uses here
         ROOT / "external" / "pyresparser" / "run.py"])
    target = out / "pyresparser"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(dist / "pyresparser-runner", target)
    probe = subprocess.run([target / f"pyresparser-runner{EXE}", ROOT / "data" / "smoke" / "smoke.pdf"],
                           capture_output=True, text=True, timeout=600)
    if '"resume"' not in probe.stdout:
        raise RuntimeError(f"pyresparser engine does not run: {probe.stdout[-500:]} {probe.stderr[-1500:]}")


def licenses(out: Path, built: list[str]) -> None:
    d = out / "LICENSES"
    d.mkdir(parents=True, exist_ok=True)
    for name, url in LICENSE_URLS.items():
        try:
            urllib.request.urlretrieve(url, d / name)
        except OSError as e:
            print(f"warning: could not fetch {name}: {e}")
    (out / "THIRD_PARTY.md").write_text(f"""# Engines shipped with ATS Simulator

These programs run as separate processes that the app calls on your resume.
They are not part of the app's own code. Each keeps its own license (copies
in LICENSES/).

| Engine | License | Source |
|---|---|---|
| OpenResume parser | AGPL-3.0 | {OPENRESUME_REPO} at commit {OPENRESUME_COMMIT}, bundled unmodified by external/openresume/bundle.mjs in https://github.com/shreyosecret/ATSResumeFilter |
| Node.js runtime | MIT and others | https://github.com/nodejs/node |
| pdf.js (pdfjs-dist 3.7.107) | Apache-2.0 | https://github.com/mozilla/pdf.js |
| pyresparser 1.0.6 | GPL-3.0 | https://github.com/OmkarPathak/pyresparser and https://pypi.org/project/pyresparser/1.0.6/ |
| spaCy 2.3.9 and en_core_web_sm 2.3.1 | MIT | https://github.com/explosion/spaCy |
| NLTK 3.8.1 and its corpora | Apache-2.0 (corpora: their own terms) | https://github.com/nltk/nltk |

Built by scripts/build_engines.py ({", ".join(built) or "nothing"} built on this platform).
To get the exact source of any engine, use the links above; the build
script shows every step that produced these files.
""", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "engines")
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "engines-work")
    ap.add_argument("--skip-openresume", action="store_true")
    ap.add_argument("--skip-pyresparser", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    a.work.mkdir(parents=True, exist_ok=True)
    built, failed = [], []
    for name, skip, fn in (("openresume", a.skip_openresume, build_openresume),
                           ("pyresparser", a.skip_pyresparser, build_pyresparser)):
        if skip:
            continue
        try:
            fn(a.out, a.work)
            built.append(name)
        except Exception as e:  # leave this engine out; the app shows it as not installed
            failed.append(name)
            print(f"\n*** {name} engine not built: {e}\n", flush=True)
    licenses(a.out, built)
    print(f"engines built: {built or 'none'}; not built: {failed or 'none'}")
    if os.environ.get("ATS_SIM_REQUIRE_ENGINES"):
        need = set(os.environ["ATS_SIM_REQUIRE_ENGINES"].split(","))
        if need - set(built):
            sys.exit(f"required engines missing: {sorted(need - set(built))}")


if __name__ == "__main__":
    main()
