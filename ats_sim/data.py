"""Loading the synthetic personas and (optionally) public Kaggle data."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESUME_DIR = DATA_DIR / "resumes"


def load_personas(path: str | Path | None = None) -> list[dict]:
    path = Path(path) if path else DATA_DIR / "personas.json"
    return json.loads(Path(path).read_text())["personas"]


def resume_path(persona_id: str, layout: str, fmt: str, root: Path = RESUME_DIR) -> Path:
    return root / fmt / layout / f"{persona_id}.{fmt}"


def load_kaggle_resumes(csv_path: str | Path, text_column: str = "Resume_str", limit: int | None = None,
                        category: str | None = None, category_column: str = "Category") -> list[tuple[str, str]]:
    """Load plain-text resumes from a Kaggle CSV as (id, text) pairs.

    Defaults match the public "Resume Dataset" (Resume.csv, columns ID,
    Resume_str, Resume_html, Category). These have no layout and no answer
    key, so they are only used as extra candidates in the ranking pool and as
    background documents for TF-IDF, never for the layout experiment.
    Check the dataset's license before redistributing anything derived from it.
    """
    import pandas as pd

    df = pd.read_csv(csv_path)
    if category:
        df = df[df[category_column].str.upper() == category.upper()]
    if limit:
        df = df.head(limit)
    id_col = "ID" if "ID" in df.columns else None
    return [
        (f"kaggle-{row[id_col] if id_col else i}", str(row[text_column]))
        for i, row in df.iterrows()
    ]
