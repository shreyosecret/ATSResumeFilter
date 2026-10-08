"""A small neural network that labels each resume line with its section.

The rule-based parser finds sections only at headings it already knows. This
tagger learns what a section looks like from labeled examples (the line text,
its neighbors, the heading above it, and its shape), so it can follow
headings it was never told about. It learns online: every confirmed or
corrected resume updates the weights with `learn()`, mixed with a replay
sample of earlier examples so new resumes do not wipe out old knowledge.

It only learns where sections are. It does not learn which candidates are
good; see the README for why outcome-based learning is left out.
"""
from __future__ import annotations

import math
import re
import warnings
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.neural_network import MLPClassifier

from ..models import ParsedResume
from ..parser import (
    _HEADING_LOOKUP, DATE_RANGE_RE, EMAIL_RE, MONTH_YEAR_RE, PHONE_RE, normalize_heading, parse_with_sections,
)
from .labels import LABELS, SECTION_LABELS, split_lines, tokens

FORMAT_VERSION = 1
_BULLET_RE = re.compile(r"^\s*(?:\(cid:127\)|[•\-\*·▪◦●■–])")
_URL_RE = re.compile(r"(?:https?://|www\.|linkedin\.com|github\.com)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d\d\b")


def _clean(line: str) -> str:
    return line.replace("(cid:127)", " ").strip().lower()


def _looks_like_heading(line: str) -> bool:
    """Shape guess used only to seed the first pass at inference time."""
    s = line.strip().rstrip(":")
    if _HEADING_LOOKUP.get(normalize_heading(s)):
        return True
    words = s.split()
    if not 1 <= len(words) <= 5 or _BULLET_RE.match(line) or re.search(r"[\d@|,.]", s):
        return False
    return s.isupper()


def heading_context(lines: list[str], is_heading: list[bool]) -> list[tuple[str, int]]:
    """For every line: the text of the nearest heading above it (consecutive
    heading lines joined, since narrow cells wrap headings) and how far up it is."""
    out, current, since, prev_heading = [], "", 0, False
    for line, h in zip(lines, is_heading):
        if h:
            current = (current + " " + line).strip() if prev_heading else line
            since = 0
        else:
            since += 1
        prev_heading = h
        out.append((current, since))
    return out


def _dense(lines: list[str], is_heading: list[bool], ctx: list[tuple[str, int]]) -> np.ndarray:
    n = len(lines)
    rows = []
    for i, line in enumerate(lines):
        s = line.strip()
        letters = [c for c in s if c.isalpha()]
        upper = sum(c.isupper() for c in letters) / len(letters) if letters else 0.0
        toks = tokens(s)
        rows.append([
            i / max(n - 1, 1), float(i == 0), float(i < 3), math.log1p(len(toks)) / 3,
            upper, float(s.istitle()), float(bool(EMAIL_RE.search(s))), float(bool(PHONE_RE.search(s))),
            float(bool(_URL_RE.search(s))), float(bool(MONTH_YEAR_RE.search(s) or DATE_RANGE_RE.search(s))),
            float(bool(_YEAR_RE.search(s))), float(bool(_BULLET_RE.match(line))), float("|" in s),
            float(s.endswith(",")), float(s.endswith(":")), s.count(",") / 5,
            sum(c.isdigit() for c in s) / max(len(s), 1), float(is_heading[i]),
            min(ctx[i][1], 20) / 20, float(ctx[i][0] == ""),
        ])
    return np.asarray(rows, dtype=np.float32)


class LineTagger:
    """MLP over hashed character and word features of a line and its context."""

    def __init__(self, hidden: tuple[int, ...] = (64,), seed: int = 0, replay_size: int = 30000):
        self.seed = seed
        self.replay_size = replay_size
        self.model = MLPClassifier(hidden_layer_sizes=hidden, alpha=1e-4, learning_rate_init=2e-3,
                                   batch_size=64, random_state=seed)
        self.rng = np.random.default_rng(seed)
        self.buffer_X: sparse.csr_matrix | None = None
        self.buffer_y: np.ndarray = np.empty(0, dtype=object)
        self.docs_seen = 0
        self.lines_seen = 0
        self.history: list[dict] = []
        self._fitted = False
        self._make_vectorizers()

    def _make_vectorizers(self) -> None:
        chars = dict(analyzer="char_wb", ngram_range=(2, 4), alternate_sign=False, n_features=2**13)
        words = dict(analyzer="word", token_pattern=r"[a-z0-9+#&]+", alternate_sign=False, n_features=2**12)
        self._v_line = HashingVectorizer(**chars)
        self._v_head = HashingVectorizer(**chars)
        self._v_prev = HashingVectorizer(**words)
        self._v_next = HashingVectorizer(**words)

    def __getstate__(self):
        d = dict(self.__dict__)
        for k in ("_v_line", "_v_head", "_v_prev", "_v_next"):
            d.pop(k, None)
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self._make_vectorizers()

    # ------------------------------------------------------------ features

    def featurize(self, lines: list[str], is_heading: list[bool]) -> sparse.csr_matrix:
        ctx = heading_context(lines, is_heading)
        clean = [_clean(l) for l in lines]
        prev = [""] + clean[:-1]
        nxt = clean[1:] + [""]
        return sparse.hstack([
            self._v_line.transform(clean),
            self._v_head.transform([_clean(c) for c, _ in ctx]),
            self._v_prev.transform(prev),
            self._v_next.transform(nxt),
            sparse.csr_matrix(_dense(lines, is_heading, ctx)),
        ], format="csr")

    # ------------------------------------------------------------ training

    def _fit_rows(self, X, y, epochs: int) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            warnings.filterwarnings("ignore", message="Got `batch_size`")  # a short resume is one batch
            for _ in range(epochs):
                order = self.rng.permutation(X.shape[0])
                self.model.partial_fit(X[order], y[order], classes=np.array(LABELS, dtype=object))
        self._fitted = True

    def _remember(self, X, y) -> None:
        self.buffer_X = X if self.buffer_X is None else sparse.vstack([self.buffer_X, X], format="csr")
        self.buffer_y = np.concatenate([self.buffer_y, y])
        extra = self.buffer_X.shape[0] - self.replay_size
        if extra > 0:  # forget the oldest rows first
            self.buffer_X, self.buffer_y = self.buffer_X[extra:], self.buffer_y[extra:]

    def doc_rows(self, lines: list[str], labels: list[str]):
        is_heading = [y == "heading" for y in labels]
        return self.featurize(lines, is_heading), np.asarray(labels, dtype=object)

    def fit(self, docs: list[tuple[list[str], list[str]]], epochs: int = 8) -> "LineTagger":
        """Batch training on many labeled documents (the starting model)."""
        rows = [self.doc_rows(l, y) for l, y in docs if l]
        X = sparse.vstack([r[0] for r in rows], format="csr")
        y = np.concatenate([r[1] for r in rows])
        self._fit_rows(X, y, epochs)
        self._remember(X, y)
        self.docs_seen += len(rows)
        self.lines_seen += X.shape[0]
        return self

    def learn(self, lines: list[str], labels: list[str], epochs: int = 6, repeat: int = 3,
              replay_ratio: int = 4, note: str = "") -> dict:
        """Online update from one labeled resume, with replay of earlier rows.

        Returns accuracy on this resume before and after the update, so the
        caller can show what changed."""
        if len(lines) != len(labels) or not lines:
            raise ValueError("lines and labels must be the same non-empty length")
        bad = set(labels) - set(LABELS)
        if bad:
            raise ValueError(f"unknown labels: {sorted(bad)}")
        before = self.predict(lines) if self._fitted else None
        X, y = self.doc_rows(lines, labels)
        parts_X, parts_y = [X] * repeat, [y] * repeat
        if self.buffer_X is not None and self.buffer_X.shape[0]:
            k = min(self.buffer_X.shape[0], replay_ratio * len(lines))
            idx = self.rng.choice(self.buffer_X.shape[0], size=k, replace=False)
            parts_X.append(self.buffer_X[idx])
            parts_y.append(self.buffer_y[idx])
        self._fit_rows(sparse.vstack(parts_X, format="csr"), np.concatenate(parts_y), epochs)
        self._remember(X, y)
        after = self.predict(lines)
        acc = lambda p: None if p is None else sum(a == b for a, b in zip(p, labels)) / len(labels)  # noqa: E731
        self.docs_seen += 1
        self.lines_seen += len(lines)
        event = {"lines": len(lines), "accuracy_before": acc(before), "accuracy_after": acc(after),
                 "changed": None if before is None else sum(a != b for a, b in zip(before, labels))}
        if note:
            event["note"] = note
        self.history.append(event)
        return event

    # ------------------------------------------------------------ inference

    def predict_proba(self, lines: list[str]) -> np.ndarray:
        """Two passes: the first uses heading shape for context, the second the
        headings the network itself found in the first."""
        if not lines:
            return np.zeros((0, len(LABELS)))
        is_heading = [_looks_like_heading(l) for l in lines]
        classes = list(self.model.classes_)
        h = classes.index("heading")
        for _ in range(2):
            P = self.model.predict_proba(self.featurize(lines, is_heading))
            is_heading = list(P[:, h] >= 0.5)
        order = [classes.index(c) for c in LABELS]
        return P[:, order]

    def predict(self, lines: list[str]) -> list[str]:
        P = self.predict_proba(lines)
        return [LABELS[i] for i in P.argmax(axis=1)] if len(P) else []

    def info(self) -> dict:
        return {"docs_seen": self.docs_seen, "lines_seen": self.lines_seen, "taught": len(self.history),
                "replay_rows": 0 if self.buffer_X is None else int(self.buffer_X.shape[0]),
                "hidden": list(self.model.hidden_layer_sizes)}


# ---------------------------------------------------------------- parsing

def sections_from_labels(lines: list[str], labels: list[str]) -> tuple[dict[str, str], str | None]:
    """Group labeled lines into the sections dict the field extractors expect."""
    groups: dict[str, list[str]] = {"header": []}
    name = None
    for line, y in zip(lines, labels):
        if y == "heading":
            continue
        if y == "name":
            name = name or line.strip()
            groups["header"].append(line)
        elif y == "contact":
            groups["header"].append(line)
        else:
            groups.setdefault(y if y in SECTION_LABELS else "other", []).append(line)
    return {k: "\n".join(v).strip() for k, v in groups.items()}, name


def parse_with_tagger(text: str, tagger: LineTagger, source: str = "<text>") -> tuple[ParsedResume, list[str], list[str]]:
    """Parse with learned sections. Returns the result, the lines and their labels."""
    lines = split_lines(text)
    labels = tagger.predict(lines)
    sections, name = sections_from_labels(lines, labels)
    return parse_with_sections("\n".join(lines), sections, source, name=name), lines, labels


def save(tagger: LineTagger, path: str | Path) -> None:
    import joblib

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    joblib.dump({"format": FORMAT_VERSION, "tagger": tagger}, tmp)
    tmp.replace(path)


def load(path: str | Path) -> LineTagger | None:
    import joblib

    try:
        d = joblib.load(path)
    except Exception:
        return None
    return d["tagger"] if isinstance(d, dict) and d.get("format") == FORMAT_VERSION else None
