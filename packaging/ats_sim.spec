# PyInstaller spec for the ATS Simulator desktop app.
#
#   python scripts/fetch_minilm_onnx.py --out build/minilm-onnx
#   python scripts/build_starting_model.py --out build/model
#   pyinstaller packaging/ats_sim.spec --noconfirm
#
# Produces dist/ATS-Simulator (Linux), dist/ATS-Simulator.exe (Windows) or
# dist/ATS Simulator.app (macOS): one program, no Python needed. PyTorch is
# left out; the semantic scorer runs the same MiniLM model through
# onnxruntime from build/minilm-onnx when that folder exists.
import subprocess
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from ats_sim import __version__  # noqa: E402

NAME = "ATS-Simulator"
ICON = str(ROOT / "packaging" / "icon.png")  # PyInstaller converts it to .ico / .icns with Pillow


def tracked(folder: str, skip: tuple[str, ...]) -> list[tuple[str, str]]:
    """Files git tracks under `folder` (so local caches and generated corpora stay out)."""
    try:
        files = subprocess.run(["git", "ls-files", folder], cwd=ROOT, capture_output=True, text=True,
                               check=True).stdout.split()
    except Exception:
        files = [str(p.relative_to(ROOT)) for p in (ROOT / folder).rglob("*") if p.is_file()]
    out = []
    for f in files:
        if any(f.startswith(s) for s in skip):
            continue
        out.append((str(ROOT / f), str(Path(f).parent)))
    return out


datas = tracked("data", ("data/resumes/", "data/kaggle/")) + tracked("results", ("results/_tmp/",))
datas += collect_data_files("ats_sim", includes=["webapp/static/**/*"])
onnx = ROOT / "build" / "minilm-onnx"
if (onnx / "model.onnx").exists():
    datas += [(str(onnx / "model.onnx"), "minilm-onnx"), (str(onnx / "tokenizer.json"), "minilm-onnx")]
else:
    print("WARNING: build/minilm-onnx missing; the app will use the LSA fallback for semantic scores")

model = ROOT / "build" / "model" / "base.joblib"  # scripts/build_starting_model.py
if model.exists():
    datas += [(str(model), "model")]
else:
    print("WARNING: build/model/base.joblib missing; the app will train its starting model on first launch")

binaries, hiddenimports = [], collect_submodules("ats_sim")
for pkg in ("en_core_web_sm", "spacy", "thinc", "pdfplumber", "pdfminer", "reportlab", "docx", "uvicorn",
            "onnxruntime", "tokenizers", "webview"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h
# spaCy ships code and data for about 70 languages; the app only reads English.
_lang = "spacy" + "/lang/"
def _keep(path: str) -> bool:
    p = path.replace("\\", "/")
    if _lang not in p:
        return True
    rest = p.split(_lang, 1)[1]
    return "/" not in rest or rest.startswith("en/")
datas = [d for d in datas if _keep(d[0])]
hiddenimports = [h for h in hiddenimports if not h.startswith("spacy.lang.") or h.startswith("spacy.lang.en")
                 or h.count(".") == 2 and h.split(".")[2] in ("char_classes", "lex_attrs", "norm_exceptions",
                                                              "punctuation", "tokenizer_exceptions")]

for pkg in ("en_core_web_sm", "spacy", "thinc", "fastapi", "starlette", "pydantic", "uvicorn"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["sklearn.utils._typedefs", "sklearn.neural_network", "multipart"],
    excludes=["torch", "sentence_transformers", "transformers", "tensorflow", "streamlit", "IPython", "jupyter",
              "matplotlib", "skillNer", "pytest", "tkinter", "pyarrow", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, upx=False, icon=ICON)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
    app = BUNDLE(coll, name="ATS Simulator.app", icon=ICON, bundle_identifier="io.github.atsresumefilter.simulator",
                 info_plist={"CFBundleShortVersionString": __version__, "NSHighResolutionCapable": True})
else:
    # One file: a single program to download and double-click.
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=False, upx=False,
              runtime_tmpdir=None, icon=ICON)
