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
    env = os.environ.get("ATS_SIM_MODEL_DIR")
    if env:
        return Path(env)
    base = os.environ.get("APPDATA") if os.name == "nt" else os.environ.get("XDG_DATA_HOME")
    return (Path(base) / "ats_sim" if base else Path.home() / ".ats_sim") / "model"


class ModelStore:
    def __init__(self, directory: str | Path | None = None, corpus: dict | None = None):
        """`corpus` narrows the starting model's training set (keyword arguments
        of corpus.documents: templates, layouts, fmts); the default is all of it."""
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
        from .corpus import documents

        self.status = "training the starting model on the synthetic corpus"
        docs = documents(cache=self.dir / "corpus", **self.corpus)
        tg = T.LineTagger().fit(list(docs.values()))
        T.save(tg, self.base_path)
        shutil.rmtree(self.dir / "corpus", ignore_errors=True)
        return tg

    def load(self) -> "ModelStore":
        with self._lock:
            tg = T.load(self.current_path) if self.current_path.exists() else None
            if tg is None:
                tg = (T.load(self.base_path) if self.base_path.exists() else None) or self.build_base()
            self.tagger = tg
            self.status = "ready"
        return self

    def predict(self, lines: list[str]) -> list[dict]:
        P = self.tagger.predict_proba(lines)
        return [{"text": l, "label": LABELS[p.argmax()], "confidence": round(float(p.max()), 3)}
                for l, p in zip(lines, P)]

    def learn(self, lines: list[str], labels: list[str]) -> dict:
        with self._lock:
            if self.tagger is None:
                raise RuntimeError("model not loaded")
            event = self.tagger.learn(lines, labels)
            event["at"] = time.strftime("%Y-%m-%d %H:%M")
            T.save(self.tagger, self.current_path)
            return event

    def reset(self) -> None:
        """Forget everything taught on this computer."""
        with self._lock:
            self.current_path.unlink(missing_ok=True)
            self.tagger = T.load(self.base_path) if self.base_path.exists() else None
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
