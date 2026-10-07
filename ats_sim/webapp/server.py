"""Local web API and static front end for the desktop app.

Binds to 127.0.0.1 only. Uploaded resumes are written to a temporary file,
analyzed and deleted; nothing is stored or sent anywhere.
"""
from __future__ import annotations

import json
import tempfile
import threading
import warnings
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..data import DATA_DIR, RESUME_DIR, load_personas, resume_path
from ..engines import OpenResumeParser, PyresparserParser, skillner_available
from ..jd import analyze_job
from ..pipeline import Candidate, screen
from ..parser import parse_resume
from ..render import FORMATS, HELD_OUT_TEMPLATES, LAYOUTS, TEMPLATES, RenderOptions, render
from ..report import FIELDS, Analyzer, posting_from_text
from ..search import QueryError, search

warnings.filterwarnings("ignore")
STATIC = Path(__file__).resolve().parent / "static"
RESULTS = DATA_DIR.parent / "results"
MAX_UPLOAD = 10 * 1024 * 1024
VERSION = "1.0.0"


class State:
    """The analyzer loads in the background so the window opens immediately."""

    def __init__(self):
        self.analyzer: Analyzer | None = None
        self.status = "starting"
        self.error: str | None = None
        self.lock = threading.Lock()

    def start(self, **kwargs) -> None:
        def run():
            try:
                self.status = "loading models"
                a = Analyzer(**kwargs)
                self.analyzer = a
                self.status = "indexing the ranking pool"
                a.warm()
                self.status = "ready"
            except Exception as e:  # surfaced in the UI
                self.error = f"{type(e).__name__}: {e}"
                self.status = "error"

        threading.Thread(target=run, daemon=True).start()

    def require(self) -> Analyzer:
        if self.analyzer is None:
            raise HTTPException(503, detail=f"Still starting up ({self.status}). Try again in a few seconds.")
        return self.analyzer


def create_app(analyzer_kwargs: dict | None = None, start: bool = True) -> FastAPI:
    app = FastAPI(title="ATS Simulator", version=VERSION, docs_url=None, redoc_url=None)
    state = State()
    app.state.sim = state
    if start:
        state.start(**(analyzer_kwargs or {}))

    personas = {p["id"]: p for p in load_personas()}

    # ---------------------------------------------------------------- meta

    @app.get("/api/status")
    def status():
        a = state.analyzer
        return {"status": state.status, "error": state.error, "ready": state.status == "ready",
                "embedding_backend": a.embedding_backend if a else None,
                "pool": len(a.pool) if a else None}

    @app.get("/api/meta")
    def meta():
        a = state.require()
        return {
            "version": VERSION,
            "postings": [{"id": j.id, "title": j.title} for j in a.postings],
            "templates": TEMPLATES, "held_out_templates": HELD_OUT_TEMPLATES, "layouts": LAYOUTS,
            "formats": FORMATS,
            "engines": {"openresume": OpenResumeParser().available(), "pyresparser": PyresparserParser().available(),
                        "skillner": skillner_available()},
            "embedding_backend": a.embedding_backend,
            "pool": {"size": len(a.pool), "synthetic": a.n_synthetic, "public": len(a.pool) - a.n_synthetic},
        }

    # ---------------------------------------------------------------- resume check

    @app.post("/api/analyze")
    async def analyze(file: UploadFile = File(...), posting_id: str = Form("all"), posting_text: str = Form(""),
                      authorized: str = Form("unknown"), sponsorship: str = Form("unknown"),
                      engines: bool = Form(True), deep_skills: bool = Form(False)):
        a = state.require()
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".pdf", ".docx"):
            raise HTTPException(400, detail="Upload a PDF or DOCX file.")
        data = await file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, detail="That file is over 10 MB.")
        if posting_text.strip():
            postings = [posting_from_text(posting_text)]
        elif posting_id != "all":
            postings = [j for j in a.postings if j.id == posting_id] or a.postings
        else:
            postings = a.postings
        answer = {"yes": True, "no": False}
        application = {"work_authorized": answer.get(authorized), "needs_sponsorship": answer.get(sponsorship)}
        with tempfile.TemporaryDirectory(prefix="ats-sim-") as tmp:
            path = Path(tmp) / f"resume{suffix}"
            path.write_bytes(data)
            try:
                result = a.analyze(path, postings=postings, application=application, use_engines=engines,
                                   with_skillner=deep_skills)
            except Exception as e:
                raise HTTPException(422, detail=f"Could not read that file ({type(e).__name__}: {e}).")
        result["file"] = file.filename
        return JSONResponse(json.loads(json.dumps(result, default=str)))

    # ---------------------------------------------------------------- screening

    def ensure(pid: str, template: str, layout: str, fmt: str) -> Path:
        path = resume_path(pid, layout, fmt, RESUME_DIR, template)
        if not path.exists():
            render(personas[pid], layout, fmt, path, RenderOptions(template=template))
        return path

    @lru_cache(maxsize=64)
    def candidates(template: str, layout: str, fmt: str, aware: bool) -> tuple:
        return tuple(Candidate(pid, parse_resume(ensure(pid, template, layout, fmt), layout_aware=aware),
                               p.get("application", {})) for pid, p in personas.items())

    def check(template, layout, fmt):
        if template not in TEMPLATES or layout not in LAYOUTS or fmt not in FORMATS:
            raise HTTPException(400, detail="Unknown template, layout or format.")

    @app.get("/api/screen")
    def screen_route(posting: str, template: str = "classic", layout: str = "single", format: str = "pdf",
                     parser: str = "naive", policy: str = "review", rank_by: str = "tfidf"):
        a = state.require()
        check(template, layout, format)
        job = next((j for j in a.postings if j.id == posting), None)
        if job is None:
            raise HTTPException(404, detail="Unknown posting.")
        cands = list(candidates(template, layout, format, parser == "layout_aware"))
        names = [s.name for s in a.scorers]
        df = screen(cands, analyze_job(job), a.scorers, primary=rank_by if rank_by in names else names[0],
                    missing_policy=policy)
        rows = []
        for r in df.to_dict("records"):
            rows.append({
                "id": r["id"], "name": r["name"], "persona_name": personas[r["id"]]["name"],
                "intent": personas[r["id"]].get("intent", ""),
                "knockout": r["knockout"], "reasons": r["knockout_reasons"], "missing": r["missing_fields"],
                "scores": {n: r[n] for n in names},
                "ranks": {n: (None if r[f"rank_{n}"] != r[f"rank_{n}"] else int(r[f"rank_{n}"])) for n in names},
            })
        return {"posting": {"id": job.id, "title": job.title}, "scorers": names, "rows": rows}

    @app.get("/api/candidate/{pid}")
    def candidate(pid: str, template: str = "classic", layout: str = "single", format: str = "pdf",
                  parser: str = "naive"):
        if pid not in personas:
            raise HTTPException(404, detail="Unknown candidate.")
        check(template, layout, format)
        c = next(c for c in candidates(template, layout, format, parser == "layout_aware") if c.id == pid)
        p = personas[pid]
        e = p["education"]
        truth = {"name": p["name"], "email": p["email"], "phone": p["phone"], "degree_level": e["degree_level"],
                 "field_of_study": e["field"], "school": e["school"], "grad_date": e["grad_date"], "gpa": e.get("gpa")}
        parsed = {f: getattr(c.parsed, f) for f in FIELDS}
        return {"id": pid, "intent": p.get("intent", ""), "parsed": parsed, "truth": truth,
                "skills": {"parsed": c.parsed.skills, "truth": p["skills"]},
                "experience": {"parsed": [f"{x.title} @ {x.company}" for x in c.parsed.experience],
                               "truth": [f"{x['title']} @ {x['company']}" for x in p["experience"]]},
                "raw_text": c.parsed.raw_text}

    @app.get("/api/sample/{pid}")
    def sample(pid: str, template: str = "classic", layout: str = "single"):
        if pid not in personas:
            raise HTTPException(404)
        check(template, layout, "pdf")
        return FileResponse(ensure(pid, template, layout, "pdf"), media_type="application/pdf")

    @app.get("/api/search")
    def search_route(q: str, k: int = 10, synonyms: bool = False, template: str = "classic",
                     layout: str = "single", format: str = "pdf", parser: str = "naive"):
        check(template, layout, format)
        cands = candidates(template, layout, format, parser == "layout_aware")
        try:
            hits = search(q, {c.id: c.text for c in cands}, k=max(1, min(k, 50)), expand_synonyms=synonyms)
        except QueryError as e:
            raise HTTPException(400, detail=str(e))
        return {"hits": [{"id": h.id, "name": personas[h.id]["name"], "intent": personas[h.id].get("intent", ""),
                          "score": h.score, "terms": h.term_counts} for h in hits]}

    # ---------------------------------------------------------------- research

    @app.get("/api/research")
    def research():
        return research_summary(RESULTS)

    @app.get("/results/{name:path}")
    def result_image(name: str):
        path = (RESULTS / name).resolve()
        allowed = {RESULTS.resolve(), (RESULTS / "parsers").resolve(), (RESULTS / "public_pool").resolve()}
        if path.parent not in allowed or path.suffix != ".png" or not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/png")

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


def research_summary(results: Path) -> dict:
    """Headline numbers from the committed experiment results, when present."""
    import pandas as pd

    out: dict = {"available": (results / "layout_summary.csv").exists(), "stats": [], "charts": []}
    if not out["available"]:
        return out
    lay = pd.read_csv(results / "layout_summary.csv")

    def f(template, parser, fmt, layout, col="f1"):
        row = lay[(lay.template == template) & (lay.parser == parser) & (lay.format == fmt) & (lay.layout == layout)]
        return None if row.empty else float(row[col].iloc[0])

    stats = [
        {"value": f("held_out_pooled", "naive", "pdf", "table"), "format": "f1",
         "label": "Table PDFs, any template", "detail": "Field-extraction F1. Only name, email, phone and GPA survive."},
        {"value": f("classic", "naive", "pdf", "two_column", "f1_drop_vs_single_pct"), "format": "pct",
         "label": "Two-column drop, dev template", "detail": "But only "
         + f"{f('held_out_pooled', 'naive', 'pdf', 'two_column', 'f1_drop_vs_single_pct'):.0f}% on held-out templates."},
        {"value": f("held_out_pooled", "naive", "docx", "textbox", "f1_drop_vs_single_pct"), "format": "pct",
         "label": "Text boxes in Word", "detail": "Drop in F1: python-docx never reads text-box content."},
    ]
    parsers = results / "parsers" / "parser_common_fields.csv"
    if parsers.exists():
        pc = pd.read_csv(parsers)
        row = pc[(pc.parser == "ensemble") & (pc.format == "pdf") & (pc.layout == "single")]
        if not row.empty:
            stats.append({"value": float(row.f1.iloc[0]), "format": "f1", "label": "Combined parsers, single column",
                          "detail": "Majority vote of ours, OpenResume and pyresparser."})
    out["stats"] = [s for s in stats if s["value"] is not None]
    charts = [
        ("layout_f1.png", "Layout robustness", "Same content in four layouts: what a simple parser recovers."),
        ("layout_templates.png", "Across five templates", "Template, parser and format all matter."),
        ("parsers/parsers.png", "Open-source parsers", "Ours vs OpenResume vs pyresparser vs a combined vote."),
        ("synonyms.png", "Synonym sensitivity", "Score lost when a resume uses different wording."),
        ("stuffing.png", "Keyword-stuffing audit", "Which scorers hidden keywords fool, and the parser fix."),
        ("public_pool/stability.png", "Ranking stability", "Movement after small wording edits, 202-resume pool."),
    ]
    out["charts"] = [{"src": f"/results/{c}", "title": t, "caption": cap} for c, t, cap in charts
                     if (results / c).exists()]
    return out
