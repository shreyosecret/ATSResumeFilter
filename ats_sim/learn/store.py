"""Where the learned model lives on this computer, and how it changes.

Nothing here is sent anywhere. The model starts from the synthetic corpus
(all templates, layouts and formats), trained on first use and cached. Every
resume a user confirms updates `current.joblib`; `reset()` deletes it and goes
back to the starting model. The replay buffer keeps hashed features of the
lines a user taught (not the text), which is still derived from the resume,
so reset removes it too.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

from . import tagger as T
from .labels import LABELS


def model_dir() -> Path:
    from ..data import user_dir

    env = os.environ.get("ATS_SIM_MODEL_DIR")
    return Path(env) if env else user_dir() / "model"


# Bump when the starting model's training set changes, so cached starting
# models are rebuilt. 2: added the 50 generated formats. 3: page geometry,
# designer and reference formats.
CORPUS_VERSION = 3


class ModelStore:
    def __init__(self, directory: str | Path | None = None, corpus: dict | None = None):
        """`corpus` narrows the starting model's training set: keyword arguments of
        corpus.documents (templates, layouts, fmts), plus `formats` (generated
        formats, default all 50; () for none) and `per_persona`."""
        self.dir = Path(directory) if directory else model_dir()
        self.corpus = corpus or {}
        self.tagger: T.LineTagger | None = None
        self.status = "not loaded"
        self._lock = threading.Lock()

    @property
    def base_path(self) -> Path:
        return self.dir / "base.joblib"

    @property
    def current_path(self) -> Path:
        return self.dir / "current.joblib"

    def ready(self) -> bool:
        return self.tagger is not None

    def build_base(self) -> T.LineTagger:
        from ..formats import SPECS
        from .corpus import documents, format_documents

        self.status = "training the starting model on the synthetic corpus"
        kw = dict(self.corpus)
        formats = kw.pop("formats", tuple(SPECS))  # generated, designer and reference formats
        per_persona = kw.pop("per_persona", 2)
        cache = self.dir / "corpus"
        # Its own folder (root=cache): the app renders the ranking pool into the shared
        # corpus folder at the same time, and a half-written file is not a PDF yet.
        docs = list(documents(root=cache, cache=cache, **kw).values())
        docs += list(format_documents(formats, per_persona=per_persona, root=cache, cache=cache).values())
        tg = T.LineTagger().fit(docs)
        tg.corpus_version = CORPUS_VERSION
        T.save(tg, self.base_path)
        shutil.rmtree(self.dir / "corpus", ignore_errors=True)
        return tg

    def _bundled_base(self) -> T.LineTagger | None:
        """The packaged desktop app ships a starting model trained at build time
        (scripts/build_starting_model.py), so a first launch does not spend many
        minutes rendering and reading the corpus."""
        import sys

        bundle = getattr(sys, "_MEIPASS", None)
        path = Path(bundle) / "model" / "base.joblib" if bundle else None
        if path is None or not path.exists():
            return None
        tg = T.load(path)
        if tg is None or getattr(tg, "corpus_version", 1) != CORPUS_VERSION:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, self.base_path)
        return tg

    def load(self) -> "ModelStore":
        with self._lock:
            tg = T.load(self.current_path) if self.current_path.exists() else None
            if tg is None:
                base = T.load(self.base_path) if self.base_path.exists() else None
                if base is None or getattr(base, "corpus_version", 1) != CORPUS_VERSION:
                    base = self._bundled_base() or self.build_base()
                tg = base
            self.tagger = tg
            self.status = "ready"
        return self

    def predict(self, lines: list[str], geo: list[list[float]] | None = None) -> list[dict]:
        P = self.tagger.predict_proba(lines, geo)
        return [{"text": l, "label": LABELS[p.argmax()], "confidence": round(float(p.max()), 3),
                 **({"geo": [round(float(v), 4) for v in geo[i]]} if geo is not None else {})}
                for i, (l, p) in enumerate(zip(lines, P))]

    def learn(self, lines: list[str], labels: list[str], geo: list[list[float]] | None = None) -> dict:
        with self._lock:
            if self.tagger is None:
                raise RuntimeError("model not loaded")
            event = self.tagger.learn(lines, labels, geo)
            event["at"] = time.strftime("%Y-%m-%d %H:%M")
            T.save(self.tagger, self.current_path)
            return event

    def reset(self) -> None:
        """Forget everything taught on this computer."""
        with self._lock:
            self.current_path.unlink(missing_ok=True)
            base = T.load(self.base_path) if self.base_path.exists() else None
            ok = base is not None and getattr(base, "corpus_version", 1) == CORPUS_VERSION
            self.tagger = base if ok else None
        if self.tagger is None:
            self.load()

    def info(self) -> dict:
        tg = self.tagger
        home = str(Path.home())
        loc = str(self.dir)
        loc = "~" + loc[len(home):] if home not in ("", "/") and loc.startswith(home) else loc
        d = {"ready": tg is not None, "status": self.status, "location": loc, "labels": list(LABELS)}
        if tg is not None:
            d.update(tg.info())
            d["history"] = tg.history[-20:]
        return d
