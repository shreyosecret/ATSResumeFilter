"""Three ways to score a resume against a job posting.

  KeywordScorer    exact match of the posting's skill terms (presence, not count)
  TfidfScorer      TF-IDF cosine similarity between resume and posting
  EmbeddingScorer  sentence-embedding similarity (all-MiniLM-L6-v2)

All scores are in [0, 1] and only comparable within one scorer.
"""
from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, field

from pathlib import Path

import numpy as np

from .models import JobAnalysis
from .skills import SkillTaxonomy, contains_term, default_taxonomy

LEVEL_WEIGHT = {"required": 2.0, "preferred": 1.0}
UNCURATED_FACTOR = 0.5


@dataclass
class ScoreDetail:
    score: float
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


class KeywordScorer:
    """Weighted share of the posting's terms that appear verbatim in the resume.

    Required terms weigh 2, preferred 1, and spaCy noun phrases (uncurated)
    half that. "Python or MATLAB" style alternatives count once if either is
    present. Presence is binary, so repeating a word does not help; adding it
    once (visibly or not) does.

    With `use_taxonomy=True` a term also matches its curated aliases and the
    specific tools listed under it (resume "ML" satisfies "machine learning",
    "Onshape" satisfies "CAD"). That is not one of the three compared scorers;
    it is a reference point for the synonym experiment.
    """

    name = "keyword"

    def __init__(self, use_taxonomy: bool = False, taxonomy: SkillTaxonomy | None = None):
        self.use_taxonomy = use_taxonomy
        self.taxonomy = taxonomy or default_taxonomy()
        if use_taxonomy:
            self.name = "keyword+taxonomy"

    def fit(self, corpus: list[str]) -> "KeywordScorer":
        return self

    def _forms(self, req) -> list[str]:
        if not (self.use_taxonomy and req.curated):
            return [req.surface]
        skill = self.taxonomy.get(req.name)
        forms = [req.surface, *(skill.surface_forms if skill else ())]
        forms += [f for s in self.taxonomy.skills if s.broader == req.name for f in s.surface_forms]
        return forms

    def explain(self, text: str, analysis: JobAnalysis) -> ScoreDetail:
        units: dict[str, list] = {}
        for req in analysis.requirements:
            units.setdefault(req.group or f"_{req.name}", []).append(req)
        total = got = 0.0
        matched, missing = [], []
        for reqs in units.values():
            w = max(LEVEL_WEIGHT[r.level] * (1 if r.curated else UNCURATED_FACTOR) for r in reqs)
            total += w
            hits = [r.surface for r in reqs if any(contains_term(text, f) for f in self._forms(r))]
            label = " / ".join(r.surface for r in reqs)
            if hits:
                got += w
                matched.append(label)
            else:
                missing.append(label)
        return ScoreDetail(got / total if total else 0.0, matched, missing)

    def score(self, text: str, analysis: JobAnalysis) -> float:
        return self.explain(text, analysis).score


class TfidfScorer:
    """Cosine similarity of TF-IDF vectors (unigrams + bigrams, raw term counts).

    Fit once on the candidate pool plus postings so IDF weights are fixed;
    variants scored later are only transformed, never refit.
    """

    name = "tfidf"

    def __init__(self, sublinear_tf: bool = False):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vec = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2),
            token_pattern=r"(?u)\b\w[\w+#]*", sublinear_tf=sublinear_tf,
        )
        self._fitted = False

    def fit(self, corpus: list[str]) -> "TfidfScorer":
        self.vec.fit(corpus)
        self._fitted = True
        return self

    def score(self, text: str, analysis: JobAnalysis) -> float:
        if not self._fitted:
            raise RuntimeError("TfidfScorer.fit(corpus) must be called before scoring")
        m = self.vec.transform([analysis.job.text, text])
        return float((m[0] @ m[1].T).toarray()[0, 0])

    def explain(self, text: str, analysis: JobAnalysis) -> ScoreDetail:
        m = self.vec.transform([analysis.job.text, text])
        contrib = m[0].multiply(m[1]).toarray()[0]
        vocab = self.vec.get_feature_names_out()
        top = [vocab[i] for i in np.argsort(contrib)[::-1][:8] if contrib[i] > 0]
        return ScoreDetail(self.score(text, analysis), matched=top)


def chunk_text(text: str, min_words: int = 4, max_words: int = 40) -> list[str]:
    """Split into lines, merge short fragments so each chunk has some context,
    and window long lines (plain-text resumes are often one huge line) so no
    chunk exceeds the embedding model's input limit."""
    chunks, buf = [], ""
    for line in text.splitlines():
        line = re.sub(r"^\W+", "", line).strip()
        if not line:
            continue
        words = line.split()
        if len(words) > max_words:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks += [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]
            continue
        buf = f"{buf} {line}".strip()
        if len(buf.split()) >= min_words:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


MINILM_ONNX_FILES = {  # the official ONNX export published alongside the PyTorch weights
    "model.onnx": "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx",
    "tokenizer.json": "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/tokenizer.json",
}


def onnx_model_dir() -> Path | None:
    """Where the ONNX copy of MiniLM is: $ATS_SIM_ONNX_DIR, inside the packaged
    app, or the user folder (scripts/fetch_minilm_onnx.py puts it there)."""
    import sys

    from .data import user_dir

    for d in (os.environ.get("ATS_SIM_ONNX_DIR"), getattr(sys, "_MEIPASS", None) and Path(sys._MEIPASS) / "minilm-onnx",
              user_dir() / "minilm-onnx"):
        if d and all((Path(d) / f).exists() for f in MINILM_ONNX_FILES):
            return Path(d)
    return None


class OnnxMiniLM:
    """all-MiniLM-L6-v2 run through onnxruntime instead of PyTorch: the same
    weights, tokenizer, 256-token limit, mean pooling and normalization as
    sentence-transformers, at a fraction of the install size (used by the
    packaged desktop app)."""

    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.tok = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tok.enable_truncation(max_length=256)
        self.tok.enable_padding(pad_id=0, pad_token="[PAD]")
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(directory / "model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}

    def encode(self, texts: list[str], normalize_embeddings: bool = True, show_progress_bar: bool = False,
               batch_size: int = 32) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok.encode_batch(texts[i:i + batch_size])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
            hidden = self.session.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0]
            m = mask[..., None].astype(np.float32)
            vec = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            if normalize_embeddings:
                vec = vec / np.clip(np.linalg.norm(vec, axis=1, keepdims=True), 1e-12, None)
            out.append(vec)
        return np.vstack(out) if out else np.zeros((0, 384), dtype=np.float32)


class EmbeddingScorer:
    """Cosine similarity of mean-pooled sentence embeddings.

    The resume and the posting are each split into line-level chunks, every
    chunk is embedded, and the chunk vectors are averaged. Chunking avoids the
    model's 256-token limit, which would otherwise silently drop the bottom of
    a resume.

    Backend: sentence-transformers all-MiniLM-L6-v2, or the same model through
    onnxruntime when PyTorch is not installed and the ONNX files are present
    (backend "all-MiniLM-L6-v2 (onnx)"). If neither can be
    loaded (no internet on first run, package missing) and `allow_fallback`
    is true, the scorer falls back to an LSA embedding (TF-IDF + truncated
    SVD fit on the corpus). The fallback is NOT a semantic model. It is there
    so the pipeline still runs, and `self.backend` records which one was used
    so results are never mislabeled. Set ATS_SIM_EMBEDDING_BACKEND=lsa to
    force the fallback, =onnx to skip PyTorch, or =minilm to make a failed
    model load an error.
    """

    name = "embedding"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", allow_fallback: bool = True):
        self.model_name = model_name
        self.model = None
        self.backend = None
        self._cache: dict[str, np.ndarray] = {}
        forced = os.environ.get("ATS_SIM_EMBEDDING_BACKEND", "").lower()
        if forced == "minilm":
            allow_fallback = False
        error = None
        if forced not in ("lsa", "onnx"):
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(model_name)
                self.backend = model_name
            except Exception as exc:  # noqa: BLE001 - any load failure tries the next backend
                error = exc
        if self.model is None and forced != "lsa" and model_name == "all-MiniLM-L6-v2" and onnx_model_dir():
            try:
                self.model = OnnxMiniLM(onnx_model_dir())
                self.backend = f"{model_name} (onnx)"
            except Exception as exc:  # noqa: BLE001
                error = exc
        if self.model is None and forced != "lsa" and (forced == "minilm" or not allow_fallback):
            raise RuntimeError(f"Could not load {model_name}") from error
        if self.model is None and forced != "lsa":
            warnings.warn(f"Could not load {model_name} ({type(error).__name__ if error else 'no ONNX copy'}); "
                          "using LSA fallback.")
        if self.model is None:
            self.backend = "lsa-fallback"
            self._lsa = None

    def fit(self, corpus: list[str]) -> "EmbeddingScorer":
        if self.model is None:
            from sklearn.decomposition import TruncatedSVD
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.pipeline import make_pipeline

            chunks = [c for doc in corpus for c in chunk_text(doc)]
            n = max(2, min(100, len(chunks) - 1))
            self._lsa = make_pipeline(
                TfidfVectorizer(stop_words="english", sublinear_tf=True), TruncatedSVD(n, random_state=0)
            ).fit(chunks)
            self._cache.clear()
        return self

    def _embed(self, chunks: list[str]) -> np.ndarray:
        todo = [c for c in chunks if c not in self._cache]
        if todo:
            if self.model is not None:
                vecs = self.model.encode(todo, normalize_embeddings=True, show_progress_bar=False)
            else:
                if self._lsa is None:
                    raise RuntimeError("LSA fallback needs EmbeddingScorer.fit(corpus) first")
                vecs = self._lsa.transform(todo)
            for c, v in zip(todo, vecs):
                n = np.linalg.norm(v)
                self._cache[c] = v / n if n else v
        return np.stack([self._cache[c] for c in chunks])

    def save_cache(self, path: str | Path) -> None:
        """Persist chunk embeddings so the next launch skips re-encoding."""
        if not self._cache or self.model is None:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        keys = list(self._cache)
        np.savez_compressed(path, keys=np.array(keys, dtype=object), vecs=np.stack([self._cache[k] for k in keys]),
                            backend=np.array(self.backend))

    def load_cache(self, path: str | Path) -> int:
        """Load embeddings saved by save_cache for the same backend; returns how many."""
        path = Path(path)
        if self.model is None or not path.exists():
            return 0
        try:
            data = np.load(path, allow_pickle=True)
            if str(data["backend"]) != self.backend:
                return 0
            self._cache.update(zip(data["keys"].tolist(), data["vecs"]))
            return len(data["keys"])
        except Exception:  # a stale or partial cache is just ignored
            return 0

    def doc_vector(self, text: str) -> np.ndarray:
        chunks = chunk_text(text) or [text or " "]
        v = self._embed(chunks).mean(axis=0)
        n = np.linalg.norm(v)
        return v / n if n else v

    def score(self, text: str, analysis: JobAnalysis) -> float:
        jd = self.doc_vector(analysis.job.text)
        return float(max(0.0, jd @ self.doc_vector(text)))

    def explain(self, text: str, analysis: JobAnalysis) -> ScoreDetail:
        return ScoreDetail(self.score(text, analysis))


def default_scorers(corpus: list[str]) -> list:
    return [s.fit(corpus) for s in (KeywordScorer(), TfidfScorer(), EmbeddingScorer())]
