"""Run pyresparser (https://github.com/OmkarPathak/pyresparser, GPL-3.0) on
local files and print one JSON object per line.

pyresparser needs spaCy 2.x, which does not install on current Python, so it
runs in its own Python 3.8 environment (see scripts/setup_external.sh) and is
called as a separate process. No pyresparser code is stored in this repo.

    $PYRESPARSER_PYTHON external/pyresparser/run.py a.pdf b.docx
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
here = os.path.dirname(os.path.abspath(sys.executable))
os.environ.setdefault("NLTK_DATA", os.path.join(here, "..", "nltk_data"))

from pyresparser import ResumeParser  # noqa: E402

for path in sys.argv[1:]:
    try:
        data = ResumeParser(path).get_extracted_data()
        print(json.dumps({"file": path, "resume": data}), flush=True)
    except Exception as e:  # report and keep going
        print(json.dumps({"file": path, "error": "%s: %s" % (type(e).__name__, e)}), flush=True)
