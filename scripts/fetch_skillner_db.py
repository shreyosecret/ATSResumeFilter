"""Download SkillNer's skill database (about 7 MB, from the SkillNER project,
MIT) into build/skillner, for the desktop build to ship.

    python scripts/fetch_skillner_db.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ats_sim.engines import SKILLNER_FILES, _ipython_stand_in  # noqa: E402

out = ROOT / "build" / "skillner"
out.mkdir(parents=True, exist_ok=True)
_ipython_stand_in()
os.chdir(out)  # SkillNer downloads into the working directory on first import
import skillNer.general_params  # noqa: E402,F401

missing = [f for f in SKILLNER_FILES if not (out / f).exists()]
if missing:
    sys.exit(f"SkillNer database files missing: {missing}")
print("SkillNer database in", out)
