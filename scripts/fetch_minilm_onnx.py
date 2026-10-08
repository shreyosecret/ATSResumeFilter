"""Download the ONNX copy of all-MiniLM-L6-v2 (about 90 MB) so the semantic
scorer runs without PyTorch. Used by the desktop build; also handy for a
light install.

    python scripts/fetch_minilm_onnx.py               # into the user folder (~/.ats_sim/minilm-onnx)
    python scripts/fetch_minilm_onnx.py --out DIR
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ats_sim.data import user_dir  # noqa: E402
from ats_sim.scorers import MINILM_ONNX_FILES  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=user_dir() / "minilm-onnx")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for name, url in MINILM_ONNX_FILES.items():
        dest = a.out / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"have {dest}")
            continue
        print(f"downloading {url}")
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    print(f"done: {a.out}")


if __name__ == "__main__":
    main()
