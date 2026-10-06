import os
import sys
from pathlib import Path

# Tests must not depend on downloading a model.
os.environ.setdefault("ATS_SIM_EMBEDDING_BACKEND", "lsa")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
