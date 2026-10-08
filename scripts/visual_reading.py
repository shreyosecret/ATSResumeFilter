"""Experiment 8: can a vision-language model read a resume page faithfully?

The app's visual check (ats_sim/visual.py) reads the rendered page and
compares it with the text an ATS extracts. That reading has to be faithful: a
reader that changes words would report differences that are not there. This
compares three readers on rendered pages of synthetic resumes, where the true
text is known exactly:

  rapidocr   PaddleOCR detection and recognition models run with onnxruntime
             (about 15 MB), the reader the app uses
  florence   Florence-2-base (230M parameters), a vision-language model,
             with its <OCR> task
  smolvlm    SmolVLM-256M-Instruct, a small chat vision-language model,
             asked to transcribe the page

Measured per page:

  recall     share of the page's words (3+ letters) whose letters appear in
             the reading; spacing is ignored, as in the visual check
  changed    share of returned words (4+ letters) whose letters appear
             nowhere on the page: invented or altered words, the failure that
             matters most here
  seconds    on this machine's CPU
  found      the image-text check: a line of text is pasted onto the page
             image (so it is visible but not in the file's text); the share of
             its words (4+ letters) the comparison reports as missing
  false      the comparison flags missing text or run-together words on an
             unmodified page (a false alarm)

    python scripts/visual_reading.py --docs 24          # results/visual/
    python scripts/visual_reading.py --readers rapidocr # skip the VLMs

The VLMs need PyTorch and transformers, and download their weights from
Hugging Face on first use; the app itself uses neither.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ats_sim.data import RESUME_DIR  # noqa: E402
from ats_sim.parser import extract_text  # noqa: E402
from ats_sim.visual import compare, render  # noqa: E402

OUT = ROOT / "results" / "visual"
READERS = {"rapidocr": "RapidOCR (app)", "florence": "Florence-2-base (VLM)", "smolvlm": "SmolVLM-256M (VLM)"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"rapidocr": "#2a78d6", "florence": "#eb6834", "smolvlm": "#1baf7a"}
PHRASES = [
    "Certifications: Six Sigma Green Belt, OSHA 30, Lean Manufacturing",
    "Languages: Spanish (fluent), Portuguese (conversational)",
    "Awards: Dean's List six semesters, Regional Hackathon finalist",
    "Tools: Tableau, Power BI, Snowflake, Airflow, Kubernetes",
    "Volunteer: Habitat for Humanity build leader, food bank coordinator",
    "Interests: competitive rowing, chess, landscape photography",
]


# ------------------------------------------------------------------ readers

def make_reader(name: str):
    if name == "rapidocr":
        from ats_sim.visual import read_page
        return read_page
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    torch.set_num_threads(max(1, torch.get_num_threads()))
    if name == "florence":
        mid = "florence-community/Florence-2-base"
        proc = AutoProcessor.from_pretrained(mid)
        model = AutoModelForImageTextToText.from_pretrained(mid, dtype=torch.float32).eval()

        def read(img):
            inp = proc(text="<OCR_WITH_REGION>", images=img, return_tensors="pt")
            with torch.no_grad():
                ids = model.generate(**inp, max_new_tokens=1024, num_beams=1, do_sample=False)
            raw = proc.batch_decode(ids, skip_special_tokens=False)[0]
            parsed = proc.post_process_generation(raw, task="<OCR_WITH_REGION>", image_size=img.size)
            return list(parsed["<OCR_WITH_REGION>"]["labels"])
        return read
    if name == "smolvlm":
        mid = "HuggingFaceTB/SmolVLM-256M-Instruct"
        proc = AutoProcessor.from_pretrained(mid)
        model = AutoModelForImageTextToText.from_pretrained(mid, dtype=torch.float32).eval()
        msgs = [{"role": "user", "content": [{"type": "image"},
                                             {"type": "text", "text": "Transcribe all the text on this page, line by line."}]}]
        prompt = proc.apply_chat_template(msgs, add_generation_prompt=True)

        def read(img):
            inp = proc(text=prompt, images=[img], return_tensors="pt")
            with torch.no_grad():
                ids = model.generate(**inp, max_new_tokens=1200, do_sample=False)
            out = proc.batch_decode(ids[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0]
            return [line for line in out.splitlines() if line.strip()]
        return read
    raise SystemExit(f"unknown reader {name}")


# ------------------------------------------------------------------ measures

def _words(text: str) -> list[str]:
    text = re.sub(r"\(cid:\d+\)", " ", text)  # unmapped bullet glyphs are not words on the page
    return [w for w in (re.sub(r"[^a-z0-9]", "", t.lower()) for t in text.split()) if w]


def _joined(words: list[str]) -> list[str]:
    """Join runs of single letters ("E D U C A T I O N", a letter-spaced heading)."""
    out, run = [], ""
    for w in words:
        if len(w) == 1 and w.isalpha():
            run += w
            continue
        if run:
            out.append(run)
            run = ""
        out.append(w)
    return out + ([run] if run else [])


def reading_scores(truth: str, lines: list[str]) -> dict:
    """Spacing-agnostic: a word counts as read when its letters appear anywhere
    in the other reading, so a reader that drops a space is not punished for it
    (the visual check compares letters, not words)."""
    T, O = _joined(_words(truth)), _joined(_words("\n".join(lines)))
    t_letters, o_letters = "".join(T), "".join(O)
    t_long, o_long = [w for w in T if len(w) >= 3], [w for w in O if len(w) >= 4]
    return {"recall": sum(w in o_letters for w in t_long) / max(len(t_long), 1),
            "changed": sum(w not in t_letters for w in o_long) / max(len(o_long), 1)}


def paste_phrase(img, phrase: str):
    """Draw a line of text into an empty band near the bottom of the page.
    None if the page has no empty band."""
    from PIL import ImageDraw, ImageFont

    gray = np.asarray(img.convert("L"))
    h, w = gray.shape
    band = int(h * 0.035)
    for top in range(int(h * 0.93), int(h * 0.55), -band // 2):
        if gray[top:top + band, int(w * 0.08):int(w * 0.92)].min() > 245:
            out = img.copy()
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", int(band * 0.6))
            except OSError:
                font = ImageFont.load_default(size=int(band * 0.6))
            ImageDraw.Draw(out).text((int(w * 0.1), top + band // 6), phrase, fill="black", font=font)
            return out
    return None


# ------------------------------------------------------------------ run

def sample_docs(n: int, seed: int = 0) -> list[Path]:
    """Stratified: hand-written templates, generated, designer and reference formats."""
    rng = random.Random(seed)
    groups = {"hand-written": [], "generated": [], "designer": [], "reference": []}
    for p in sorted(RESUME_DIR.glob("*/pdf/*/*.pdf")):
        fam = p.parts[-4]
        g = ("generated" if re.fullmatch(r"f\d\d", fam) else "designer" if re.fullmatch(r"d\d\d", fam)
             else "reference" if re.fullmatch(r"r\d\d", fam) else "hand-written")
        groups[g].append(p)
    per = max(1, n // len(groups))
    return [p for g in groups.values() for p in rng.sample(g, min(per, len(g)))]


def run(n_docs: int, readers: list[str]) -> pd.DataFrame:
    docs = sample_docs(n_docs)
    pages = []
    for k, path in enumerate(docs):
        img = render(path, max_pages=1)[0]
        phrase = PHRASES[k % len(PHRASES)]
        pages.append((path, extract_text(path), img, phrase, paste_phrase(img, phrase)))
    rows = []
    for name in readers:
        print(f"loading {name} ...", flush=True)
        read = make_reader(name)
        for path, truth, img, phrase, pasted in pages:
            t0 = time.time()
            lines = read(img)
            secs = time.time() - t0
            sc = reading_scores(truth, lines)
            plain = compare(truth, lines)
            row = dict(reader=name, doc=str(path.relative_to(RESUME_DIR)), seconds=secs, **sc,
                       false=bool(plain["missing"] or plain["glued"]), found=None)
            if pasted is not None:
                got = compare(truth, read(pasted))
                # words of 4+ letters that are not already in the resume's text
                want = {w for w in _words(phrase) if len(w) >= 4 and w not in "".join(_words(truth))}
                said = set(_words(" ".join(got["missing"])))
                row["found"] = len(want & said) / len(want)
            rows.append(row)
            print(f"{name:9s} {row['doc']:38s} recall {sc['recall']:.2f} changed {sc['changed']:.2f} "
                  f"{secs:5.1f}s found {row['found']}", flush=True)
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> dict:
    out = {}
    for name, sub in df.groupby("reader"):
        out[name] = {"pages": int(len(sub)), "recall": round(float(sub.recall.mean()), 3),
                     "changed": round(float(sub.changed.mean()), 3),
                     "seconds": round(float(sub.seconds.median()), 1),
                     "found": round(float(sub.found.dropna().mean()), 3),
                     "false_alarms": int(sub["false"].sum())}
    return out


def chart(s: dict, path: Path) -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "font.size": 10,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
    })
    names = [r for r in READERS if r in s]
    panels = [("recall", "Words read (recall)"), ("changed", "Words changed or invented"),
              ("found", "Image text found"), ("seconds", "Seconds per page (CPU)")]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.9))
    for ax, (key, title) in zip(axes, panels):
        vals = [s[r][key] for r in names]
        bars = ax.bar(range(len(names)), vals, color=[COLORS[r] for r in names], width=0.6)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}" if key != "seconds" else f"{v:.0f}",
                    ha="center", va="bottom", fontsize=8.5, color=INK2)
        ax.set_xticks(range(len(names)), [READERS[r].replace(" (", "\n(") for r in names], fontsize=8)
        ax.set_title(title)
        if key != "seconds":
            ax.set_ylim(0, 1.1)
    fig.suptitle(f"Reading rendered resume pages ({s[names[0]]['pages']} pages, synthetic, true text known)",
                 x=0.01, ha="left", fontsize=10.5, color=INK2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=int, default=24)
    ap.add_argument("--readers", default=",".join(READERS))
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--replot", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.replot:
        chart(json.loads((a.out / "summary.json").read_text(encoding="utf-8"))["readers"], a.out / "visual_reading.png")
        return
    df = run(a.docs, a.readers.split(","))
    df.to_csv(a.out / "visual_reading.csv", index=False)
    s = summarize(df)
    (a.out / "summary.json").write_text(json.dumps({"docs": a.docs, "readers": s}, indent=2), encoding="utf-8")
    chart(s, a.out / "visual_reading.png")
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
