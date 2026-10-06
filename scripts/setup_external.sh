#!/usr/bin/env bash
# Install the optional open-source engines used by scripts/benchmark_parsers.py
# and scripts/check_resume.py. Nothing from these projects is committed to this
# repo; they are downloaded into ../third_party (override with THIRD_PARTY=...).
#
#   OpenResume  AGPL-3.0  https://github.com/xitanggg/open-resume   (needs node >= 18)
#   pyresparser GPL-3.0   https://github.com/OmkarPathak/pyresparser (needs uv; runs on Python 3.8 + spaCy 2)
#   SkillNer    MIT       https://github.com/AnasAito/SkillNER       (installed into the current Python)
#
# Afterwards export the two variables this script prints.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
tp="${THIRD_PARTY:-$here/../third_party}"
mkdir -p "$tp"

echo "== OpenResume"
[ -d "$tp/open-resume" ] || git clone --depth 1 https://github.com/xitanggg/open-resume "$tp/open-resume"
(cd "$here/external/openresume" && npm install --silent)

echo "== pyresparser (isolated Python 3.8 environment)"
uv python install 3.8
[ -d "$tp/pyresparser-env" ] || uv venv -q -p 3.8 "$tp/pyresparser-env"
VIRTUAL_ENV="$tp/pyresparser-env" uv pip install -q "spacy==2.3.9" "pyresparser==1.0.6" "nltk==3.8.1" \
  "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-2.3.1/en_core_web_sm-2.3.1.tar.gz"
"$tp/pyresparser-env/bin/python" -m nltk.downloader -q -d "$tp/pyresparser-env/nltk_data" \
  stopwords words punkt averaged_perceptron_tagger

echo "== SkillNer"
python -m pip install -q skillNer ipython   # ipython is an undeclared SkillNer dependency
python -m spacy download en_core_web_lg

cat <<MSG

Done. Set these before running the benchmark or check_resume:
  export OPENRESUME_DIR="$tp/open-resume"
  export PYRESPARSER_PYTHON="$tp/pyresparser-env/bin/python"
MSG
