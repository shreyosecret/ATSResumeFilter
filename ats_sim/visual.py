"""What a person sees on the page, compared with what an ATS extracts.

An ATS reads the text stored in a PDF. A recruiter reads the rendered page.
They usually agree, but not always: text drawn as an image (a logo-style
header, a skills graphic, a scanned page) is visible and has no stored text,
and a PDF can store words without the spaces a reader sees between them.

This module renders each page, reads it with an OCR model (RapidOCR: PaddleOCR
models run with onnxruntime, Apache-2.0, about 15 MB), and lines the two
readings up letter by letter. It reports what is on the page but missing from
the text, and words that run together in the text but not on the page.

OCR is used as a reference reading, not as the ATS: it can misread a letter,
so only differences of a dozen letters or more count as missing. Experiment 8
(scripts/visual_reading.py) compares it with small vision-language models,
which read more loosely and sometimes change words.
"""
from __future__ import annotations

import difflib
import re
import time
from functools import lru_cache
from pathlib import Path

MIN_MISSING = 12  # letters; shorter differences are OCR noise
MAX_PAGES = 4
_SKIP = re.compile(r"@|/|www\.|https?:|\.(?:com|org|edu|net|io)\b", re.IGNORECASE)


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        import pypdfium2  # noqa: F401
    except Exception:
        return False
    return True


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    # A rendered PDF page is upright. The text-direction classifier squeezes a
    # long line into 192 pixels and sometimes turns it upside down, and the
    # line is then misread (seen on a full-width line of 60 characters).
    engine.use_angle_cls = False
    return engine


def render(path: str | Path, scale: float = 2.0, max_pages: int = MAX_PAGES) -> list:
    """Each page as an RGB image (scale 2 is 144 dots per inch)."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        return [doc[i].render(scale=scale).to_pil().convert("RGB") for i in range(min(len(doc), max_pages))]
    finally:
        doc.close()


def read_page(image) -> list[str]:
    """Lines of text OCR finds on one page image, top to bottom."""
    import numpy as np

    result, _ = _engine()(np.array(image))
    rows = sorted(result or [], key=lambda r: (round(r[0][0][1] / 8), r[0][0][0]))
    return [r[1] for r in rows]


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _letters(words: list[str]) -> tuple[str, list[int]]:
    chars, owner = [], []
    for k, w in enumerate(words):
        for ch in _norm(w):
            chars.append(ch)
            owner.append(k)
    return "".join(chars), owner


def compare(extracted: str, visible_lines: list[str]) -> dict:
    """Line up the extracted text with what OCR saw on the page."""
    ext = re.findall(r"\S+", re.sub(r"\(cid:\d+\)", " ", extracted))
    vis = [w for line in visible_lines for w in line.split()]
    E, e_own = _letters(ext)
    V, v_own = _letters(vis)
    sm = difflib.SequenceMatcher(None, E, V, autojunk=False)
    missing, missing_letters, matched = [], 0, 0
    seen_by: dict[int, set[int]] = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
            for a, b in zip(range(i1, i2), range(j1, j2)):
                seen_by.setdefault(e_own[a], set()).add(v_own[b])
        elif tag in ("insert", "replace") and (j2 - j1) - (i2 - i1) >= MIN_MISSING:
            # OCR reads straight across a row, the text may put a right-aligned
            # date or a second column elsewhere: a word is missing only if it is
            # nowhere in the extracted text.
            words = [k for k in sorted(set(v_own[j1:j2])) if _norm(vis[k]) and _norm(vis[k]) not in E]
            lost = sum(len(_norm(vis[k])) for k in words)
            if lost >= MIN_MISSING:
                missing.append(" ".join(vis[k] for k in words))
                missing_letters += lost
    glued = []
    for k, parts in sorted(seen_by.items()):
        word = ext[k]
        core = re.sub(r"[^A-Za-z0-9]", "", word)
        if len(parts) < 2 or len(core) < 8 or _SKIP.search(word):
            continue
        pieces = [vis[j] for j in sorted(parts)]
        if "".join(map(_norm, pieces)) == _norm(word) and sum(len(_norm(p)) >= 2 for p in pieces) >= 2:
            glued.append({"read": word, "seen": " ".join(pieces)})
    return {
        "visible_letters": len(V),
        "extracted_letters": len(E),
        "coverage": round(matched / len(V), 3) if V else 1.0,
        "missing": missing,
        "missing_share": round(missing_letters / len(V), 3) if V else 0.0,
        "glued": glued,
        "image_only": len(V) >= 60 and len(E) < 0.2 * len(V),  # a stray logo is not a page
    }


def check(path: str | Path, extracted: str) -> dict | None:
    """Render, read and compare a PDF. None when OCR is not installed or the
    file is not a PDF (a Word file has no fixed page to render)."""
    path = Path(path)
    if path.suffix.lower() != ".pdf" or not available():
        return None
    t0 = time.time()
    lines = [line for img in render(path) for line in read_page(img)]
    out = compare(extracted, lines)
    # What OCR read, for parsing a scanned page. OCR sets "@" apart as its own
    # word ("ana @ example.com"); joining it back is the one cleanup applied.
    out["text"] = re.sub(r"(\w) *@ *(\w)", r"\1@\2", "\n".join(lines))
    out["seconds"] = round(time.time() - t0, 1)
    return out


def risks(result: dict | None) -> list[dict]:
    """Risk entries in the format of report.diagnose."""
    if result is None:
        return []
    out = []
    if result["image_only"]:
        out.append({"level": "bad", "title": "The page is an image",
                    "detail": "Almost none of the text a reader sees is stored as text, as in a scanned resume. "
                              "An ATS without OCR reads an empty resume; the 'With OCR' column shows what one that runs OCR "
                              "would read. Save it again from the original document."})
    elif result["missing"]:
        ex = "; ".join(f"“{m[:60]}”" for m in result["missing"][:3])
        out.append({"level": "bad" if result["missing_share"] >= 0.05 else "warn",
                    "title": "Text on the page that an ATS cannot read",
                    "detail": f"Visible on the page but not in the file's text, probably drawn as an image: {ex}. "
                              "Put anything that matters in real text."})
    if result["glued"]:
        ex = "; ".join(f"“{g['read'][:40]}”" for g in result["glued"][:3])
        out.append({"level": "warn", "title": f"{len(result['glued'])} run-together word(s) in the text",
                    "detail": f"The page shows spaces that the file's text does not have: {ex}. Some extractors "
                              "read these as one long word, so keyword search misses the words inside."})
    if not out:
        out.append({"level": "ok", "title": "The page and its text agree",
                    "detail": f"An OCR reading of the page matched the extracted text "
                              f"({result['coverage']:.0%} of the visible letters)."})
    return out
