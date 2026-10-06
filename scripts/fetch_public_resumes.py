"""Download the public "Resume Dataset" (Kaggle: snehaanbhawal/resume-dataset,
license CC0 1.0) from its Hugging Face mirror, so no Kaggle account is needed.

    python scripts/fetch_public_resumes.py          # -> data/kaggle/Resume.csv (gitignored)

The resumes are real (scraped from livecareer.com by the dataset author and
released as CC0). They are used only as anonymous distractors in ranking
pools; nothing derived from an individual resume is committed to this repo.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = "https://huggingface.co/datasets/opensporks/resumes/resolve/main/Resume/Resume.csv"
DEST = Path(__file__).resolve().parent.parent / "data" / "kaggle" / "Resume.csv"


def main() -> Path:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"already present: {DEST}")
        return DEST
    print(f"downloading {URL}")
    urllib.request.urlretrieve(URL, DEST)
    print(f"saved {DEST.stat().st_size / 1e6:.1f} MB to {DEST}")
    return DEST


if __name__ == "__main__":
    main()
    sys.exit(0)
