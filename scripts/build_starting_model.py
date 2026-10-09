"""Train the learned parser's starting model once and save it, for the
desktop build to ship (so the app does not train it on a user's first launch).

    python scripts/build_starting_model.py --out build/model
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ats_sim.learn.store import CORPUS_VERSION, ModelStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("build/model"))
    a = ap.parse_args()
    t = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        store = ModelStore(Path(tmp))
        tagger = store.build_base()
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "base.joblib").write_bytes(store.base_path.read_bytes())
    print(f"starting model (corpus version {CORPUS_VERSION}, {getattr(tagger, 'real_docs', 0)} real resumes): {tagger.info()} in {time.time() - t:.0f}s -> "
          f"{a.out / 'base.joblib'}")


if __name__ == "__main__":
    main()
