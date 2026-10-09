"""Download the public "Resume Dataset" (Kaggle: snehaanbhawal/resume-dataset,
license CC0 1.0) from its Hugging Face mirror, so no Kaggle account is needed.

    python scripts/fetch_public_resumes.py          # -> data/kaggle/Resume.csv (gitignored)
    python scripts/fetch_public_resumes.py --pdfs   # also the 2,484 PDFs -> data/kaggle/pdf/ (about 120 MB)

The resumes are real (scraped from livecareer.com by the dataset author and
released as CC0). They are used as anonymous distractors in ranking pools
and, with --pdfs, as experiment 9's real-resume test set
(scripts/real_resumes.py). Nothing derived from an individual resume is
committed to this repo; only aggregate results are.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://huggingface.co/datasets/opensporks/resumes/resolve/main/Resume/Resume.csv"
DEST = Path(__file__).resolve().parent.parent / "data" / "kaggle" / "Resume.csv"


API = "https://huggingface.co/api/datasets/opensporks/resumes"
PDF_URL = "https://huggingface.co/datasets/opensporks/resumes/resolve/main/{}"
PDF_DIR = DEST.parent / "pdf"


def main() -> Path:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"already present: {DEST}")
        return DEST
    print(f"downloading {URL}")
    urllib.request.urlretrieve(URL, DEST)
    print(f"saved {DEST.stat().st_size / 1e6:.1f} MB to {DEST}")
    return DEST


def fetch_pdfs(workers: int = 8) -> int:
    """Every resume's PDF, as data/kaggle/pdf/<CATEGORY>/<ID>.pdf."""
    import json
    from concurrent.futures import ThreadPoolExecutor

    with urllib.request.urlopen(API, timeout=60) as r:
        files = [s["rfilename"] for s in json.loads(r.read())["siblings"] if s["rfilename"].endswith(".pdf")]

    def one(name: str) -> bool:
        dest = PDF_DIR / Path(name).parent.name / Path(name).name
        if dest.exists() and dest.stat().st_size > 1000:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        for attempt in range(4):
            try:
                urllib.request.urlretrieve(PDF_URL.format(name), tmp)
                tmp.replace(dest)
                return True
            except OSError:
                import time

                time.sleep(2 ** attempt)
        print("failed:", name)
        return False

    with ThreadPoolExecutor(workers) as ex:
        got = sum(ex.map(one, files))
    print(f"{got} PDFs downloaded, {len(files)} in the dataset, in {PDF_DIR}")
    return got


if __name__ == "__main__":
    main()
    if "--pdfs" in sys.argv:
        fetch_pdfs()
    sys.exit(0)
