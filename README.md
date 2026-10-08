# ATS Filter Simulator

[![tests](https://github.com/shreyosecret/ATSResumeFilter/actions/workflows/tests.yml/badge.svg)](https://github.com/shreyosecret/ATSResumeFilter/actions/workflows/tests.yml)

A Python simulator that parses resumes the way a simple applicant tracking system does, screens them with knockout rules, ranks them against a job posting with three scoring methods, and runs controlled experiments to measure which resume choices actually change the outcome.

This is **a simulator modeled on documented ATS behavior**, not a reproduction of any vendor's system. Workday, Greenhouse, Lever and iCIMS are proprietary, and nothing here says how any of them scores a real person.

## The app

![Resume check](docs/screenshots/resume-check.png)

A desktop-style app for checking a resume and exploring how screening works. It runs entirely on your computer: uploaded resumes are read, analyzed and deleted, and the server only listens on 127.0.0.1.

| Screen | What it does |
|---|---|
| **Resume check** | Drop in a PDF or Word resume. Tabs for an overview (parsing checks, worst first, and skills found), job matches (screening result and percentile rank per scorer for every posting, including one you paste in, expandable to the terms found and missing), a parser-by-parser comparison, and the extracted text |
| **Screening** | The recruiter's view: 16 fictional candidates screened and ranked. Switch template, layout, file format or parser and watch who gets screened out; click a candidate to compare what the parser read with what the resume says |
| **Boolean search** | Recruiter-style keyword queries with AND, OR, NOT, quotes and parentheses |
| **Research** | The headline findings, drawn as interactive charts (hover for values and 95% intervals, or switch any chart to a table) |

**Run it**

- Double-click `launchers/ATS Simulator.command` (macOS) or `launchers/ATS Simulator.bat` (Windows), or run `bash launchers/run.sh` (Linux). The first run creates a private Python environment and installs everything (a few minutes, once); later runs open in seconds.
- Or by hand: `pip install -e ".[embeddings,desktop]"`, `python -m spacy download en_core_web_sm`, then `ats-sim`.

With `pywebview` installed (the `desktop` extra) the app opens in its own window; otherwise it opens in your browser. `ats-sim --browser` forces the browser. Light and dark themes follow the system, with a toggle. The interface uses the Inter typeface (SIL Open Font License), bundled so the app works offline. The first launch takes about a minute while the language model indexes the comparison resumes; that index is cached, so later launches take seconds. The open-source parsers and SkillNer appear automatically when installed (`scripts/setup_external.sh`).

<table><tr>
<td><img src="docs/screenshots/job-matches.png" alt="Job matches: percentile rank per scorer, expandable details"></td>
<td><img src="docs/screenshots/research-dark.png" alt="Research charts, dark theme"></td>
</tr><tr>
<td><img src="docs/screenshots/screening.png" alt="Screening view"></td>
<td><img src="docs/screenshots/candidate-dark.png" alt="Candidate details, dark theme"></td>
</tr></table>

**Shipping notes.** The app installs with pip from a checkout of this repository; the launchers wrap that so non-technical users can double-click. It is not yet a signed stand-alone installer: bundling it with PyInstaller is possible but would carry PyTorch (for the semantic scorer, roughly 1 to 2 GB) and must be built on each operating system. Without the `embeddings` extra the app still works, using a lighter LSA fallback that it labels as such. The older Streamlit developer dashboard is still available with `streamlit run app.py`.

## What it models (and what it deliberately does not)

The popular claim that "75% of resumes are auto-rejected by robots" has no solid study behind it. Documented ATS behavior comes down to three things, and the simulator models exactly those:

| Stage | Real-world behavior | Here |
|---|---|---|
| **Parse** | Turn the file into fields (contact, education, experience, skills) | `ats_sim/parser.py`: pdfplumber / python-docx, heading detection, regex fields. Two reading-order modes: naive (text order) and layout-aware (tables, boxes, columns) |
| **Knockout** | Reject on application questions: work authorization, graduation date, minimum GPA, degree field | `ats_sim/knockout.py`: rule-based, with an explicit policy for fields the parser could not find |
| **Search and rank** | Recruiters run Boolean keyword searches; some newer systems add a match score | `ats_sim/search.py` (Boolean top-k) and `ats_sim/scorers.py` (keyword, TF-IDF, embedding) |

There is **no single magic score that rejects people**. Scores only order candidates who passed the knockouts. A human decides what happens next.

Knockouts are usually application-form questions, not resume parsing. Many forms are prefilled from the parse, though, and a candidate who does not correct the autofill is screened on what the parser extracted. The default here reads education fields from the parse (the uncorrected-autofill case). Work authorization always comes from the candidate's answers, because no parser can know it.

## Quick start

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm

python scripts/build_corpus.py                 # 16 personas x 5 templates x 2 formats x 4 layouts = 640 resumes
python scripts/run_experiments.py --require-minilm      # results/ (fails rather than falling back to LSA)
ats-sim                                        # the app (after pip install -e ".[embeddings,desktop]")
streamlit run app.py                           # older developer dashboard
pytest                                         # 60 tests (also run by GitHub Actions on every push)

# optional: rerun the ranking experiments with ~190 public resumes as distractors
python scripts/fetch_public_resumes.py         # CC0 dataset, no Kaggle account needed
python scripts/run_experiments.py --require-minilm --public-pool data/kaggle/Resume.csv --out results/public_pool

# optional: open-source engines (OpenResume, pyresparser, SkillNer), then benchmark and check a resume
bash scripts/setup_external.sh                 # prints OPENRESUME_DIR and PYRESPARSER_PYTHON to export
python scripts/benchmark_parsers.py            # results/parsers/
python scripts/run_experiments.py --require-minilm --with-skillner
python scripts/check_resume.py my_resume.pdf   # report in private/ (gitignored)
```

The first run downloads `all-MiniLM-L6-v2` (about 90 MB). Without `--require-minilm`, a failed download falls back to an LSA embedding with a warning, and every chart and table is labeled with the backend actually used. All committed results use MiniLM.

## Pipeline

1. **Parser** (`parser.py`). A line counts as a section heading only if it is a known heading on its own line; fields come from regexes inside the detected sections. Two reading-order modes share those exact rules:
   - *naive*: pdfplumber's text order for PDF; body paragraphs and tables for DOCX (like many simple readers, no text boxes, headers or footers).
   - *layout-aware*: ruled tables are read cell by cell, bordered boxes as blocks, and a column gutter, if found, splits the page so the left column is read before the right. Boxes floating beside the main text are read after it. DOCX text boxes are read after their anchor paragraph.
2. **Job description analyzer** (`jd.py`). Splits a posting into Requirements / Preferred / Responsibilities, finds skills from the curated list in `data/skills.json`, and adds spaCy noun phrases as lower-weight uncurated terms. It handles "Python or MATLAB" as alternatives and demotes skills after cues like "ideally" or "a plus". Degree and graduation lines feed the knockouts, not the skill list.
3. **Knockout filter** (`knockout.py`). Graduation window, minimum GPA, minimum degree level, accepted degree fields, work authorization and sponsorship. A field the parser could not find becomes `REVIEW` (default), `REJECT`, or `PASS`, depending on `missing_policy`.
4. **Scorers** (`scorers.py`).
   - *Keyword*: share of the posting's terms present verbatim (required weighs 2, preferred 1, noun phrases half). Presence is binary, so repetition does not help.
   - *TF-IDF*: cosine similarity, unigrams and bigrams, fit once on the pool so variants never change the IDF weights.
   - *Embedding*: `all-MiniLM-L6-v2`. The text is split into line chunks (long lines are windowed to 40 words), each chunk is embedded, and the vectors are mean-pooled. Chunking avoids the model's 256-token limit, which would otherwise silently drop most of a resume.
   - *Keyword+taxonomy* (reference only): keyword match that also accepts curated aliases and narrower tools ("ML" counts as "machine learning", "Onshape" as "CAD").
5. **Recruiter search** (`search.py`). `(Python OR MATLAB) AND "GMP" NOT intern`, with implicit AND, `-term`, phrases and parentheses. Results are ranked by log-damped term counts. Synonym expansion is optional.
6. **Report** (`app.py`). A Streamlit dashboard: pick a posting, layout, format, template and parser mode, then see each resume's parsed fields next to its answer key, the raw text the parser saw, knockout result, three scores, ranks, live Boolean search, and the experiment charts. You can upload your own resume; it is parsed in the session and deleted.

## Data

- `data/personas.json`: 16 synthetic, fictional candidates written for this project (example.com emails, 555 phone numbers, invented schools and employers). They span ML, bioprocess, mechanical and off-domain profiles, and include deliberate edge cases: a missing GPA, a sponsorship need, a late graduation date, a non-matching degree, and candidates who write "ML" or "Onshape" instead of the posting's wording. **This file is the hand-written answer key** for field extraction.
- Five templates, rendered by `ats_sim/render.py`. The same content goes into each:

  | Template | Status | Modeled on | Conventions |
  |---|---|---|---|
  | **classic** | development | (the parser was written against it) | ALL-CAPS headings, "B.S. in Field", "Title \| Company \| dates" |
  | **modern** | held out | designer-style templates | title-case headings, profile summary, contact icons, "Bachelor of Science, Field", right-aligned dates, grouped skills, "Skills & Certifications" heading |
  | **latex** | held out | the popular one-page LaTeX student template | school \| location and degree \| date-range rows, title \| dates then company \| location, "Technical Skills" by category |
  | **career_center** | held out | university career-center handouts | "RELEVANT EXPERIENCE", company line then title line, GPA inside the degree line, one line of "Label: items;" skill groups |
  | **hybrid** | held out | skills-first functional/hybrid resumes | qualifications summary, one bullet per skill under "Core Competencies", seasonal dates ("Summer 2025"), year-only graduation, "Education & Certifications" |

  The held-out templates were written after the parser's field rules were frozen, and those rules were never changed afterwards. The templates were chosen for realism, not to make the parser fail, but they were written by someone who knew the parser, so treat them as a convenience sample of real conventions, not a random draw. Tests fail if the parser is ever tuned to them.
- `data/samples/`: one candidate in every template and layout (20 PDFs) to browse on GitHub. `data/resumes/` (all 640 files) is generated by `build_corpus.py` and not committed.
- `data/jobs/*.json`: three synthetic postings (ML intern, biologics process engineer, mechanical design engineer), each with knockout rules.
- **Public resumes (optional).** `scripts/fetch_public_resumes.py` downloads the Kaggle "Resume Dataset" (snehaanbhawal/resume-dataset, CC0 1.0) from its Hugging Face mirror into the gitignored `data/kaggle/`. 186 resumes from the Engineering, IT, Aviation and Automobile categories join every ranking pool as distractors. They have no layout and no answer key, so they never enter the layout experiment, and nothing derived from an individual resume is committed. No LinkedIn scraping, and no real resumes used without permission.

## Results

All numbers come from `results/RESULTS.md` (16-resume pool) and `results/public_pool/RESULTS.md` (202-resume pool), produced by `scripts/run_experiments.py` with all-MiniLM-L6-v2. Brackets are 95% bootstrap confidence intervals (2,000 resamples). For a single template they resample the 16 personas; for the pooled held-out templates they resample templates and then personas. Drops are paired against the same personas' single-column results.

### 1. Layout robustness: the strongest result

640 resumes: 16 personas x 5 templates x 2 formats x 4 layouts, each read by both parser modes, micro-F1 over 10 fields.

![Field extraction F1 by layout](results/layout_f1.png)

Naive parser, PDF, F1 by template (drop vs. the same template's single column in parentheses):

| Template | Single column | Two column | Table | Text boxes |
|---|---|---|---|---|
| classic (dev) | 1.00 | 0.67 (-33%) | 0.37 (-63%) | 0.65 (-35%) |
| modern | 0.51 | 0.49 (-4%, n.s.) | 0.37 (-27%) | 0.29 (-44%) |
| latex | 0.74 | 0.70 (-5%) | 0.37 (-50%) | 0.54 (-27%) |
| career_center | 0.81 | 0.74 (-9%) | 0.37 (-54%) | 0.60 (-25%) |
| hybrid | 0.36 | 0.33 (-7%) | 0.37 (+5%) | 0.24 (-34%) |
| **held-out, pooled** | **0.64 [0.44, 0.78]** | **0.59, -7% [2, 11]** | **0.37, -41% [15, 52]** | **0.44, -30% [25, 41]** |

DOCX: single column, two column and table parse the same as single column in every template except hybrid two-column (-15%). DOCX text boxes cost 24% to 74% (pooled -51% [35, 66]).

What holds across templates, and what does not:

- **Tables are the most robust finding.** A table PDF scores 0.37 in every template: only name, email, phone and GPA survive, because the section label and its content share a line ("EDUCATION B.S. in Computer Science") and no section is ever detected.
- **Text boxes cost 25% to 44% as PDF and 24% to 74% as DOCX in every template.** In PDF the contact box shares lines with the name; python-docx never sees text-box content at all, so contact details and skills disappear.
- **The two-column penalty is template-dependent, and the 33% from the development template was the outlier.** On held-out templates two-column PDFs cost 4% to 9% (pooled 7%). The development template is the only one the parser reads perfectly, so it had the most to lose. On the others, wording conventions had already cost the fields that column interleaving breaks (experience, skills), and a field can only be lost once.
- **But two-column still breaks the fields that knockouts depend on** (see below). In latex and career_center the degree and its date share a row; squeezed into a narrow sidebar it wraps, and the interleaved reading pulls a job date into the education section as the graduation date.
- **Format matters as much as layout.** Two-column and table designs saved as DOCX parsed like single column, because Word tables are read cell by cell in order.
- **Wording conventions matter as much as layout.** Single-column F1 ranges from 0.36 to 1.00 across templates. Each held-out template trips different rules: "Bachelor of Science, Field" (no "in") hides the field of study, "Title, Company" or a company line above the title hides the employer, seasonal dates ("Summer 2025") and year-only graduation dates are not parsed, and "Skills & Certifications" or "Education & Certifications" are not recognized as headings.

![Layout x template x parser](results/layout_templates.png)

A note on `(cid:127)`: that is how pdfminer prints a bullet glyph it cannot map to Unicode. It does not matter for comma-separated skills, but in the hybrid template, which lists one skill per bullet, the PDF bullets cannot act as separators and the whole list becomes one garbage item. That is why hybrid single column scores 0.36 as PDF but 0.79 as DOCX, where the bullet is a real "•". Real PDFs vary in how their bullets extract; this generator's do not.

#### A layout-aware parser

The layout-aware mode reads tables cell by cell, boxes as blocks, and detected columns one at a time, with the same field rules.

| Pooled held-out templates | Naive | Layout-aware |
|---|---|---|
| PDF table | 0.37 | 0.56 |
| PDF text boxes | 0.44 | 0.64 (= single column) |
| PDF two column | 0.59 | 0.63 |
| DOCX text boxes | 0.35 | 0.72 (= single column) |

It recovers most of the layout loss in every template (classic tables 0.37 to 1.00, two columns 0.67 to 0.98), but it cannot fix wording: a layout scores above its template's single column only by accident (hybrid two-column reaches 0.49 against 0.36, because text from an unrecognized summary section happens to land in the skills list). In one case it makes things slightly worse: modern two-column falls from 0.49 to 0.47, because clean reading order lets the parser find every "Title, Company" line and misread each one. Better reading order can turn misses into confident wrong answers.

**Bugs found by the new templates (disclosed because they affect what is held out).** Evaluating on latex and career_center exposed two flaws in the layout-aware column detector: it mistook right-aligned dates for a second column, and it accepted a "gutter" that cut through a long wrapped line. Both were fixed with general typesetting rules (body-text columns are left-aligned; a gutter never splits a line of continuous text), and a test now requires layout-aware and naive reading to agree on every single-column resume in every template. Before the fix, layout-aware single-column F1 was 0.70 for latex and 0.74 for career_center (now 0.74 and 0.81, equal to naive). Because the fix was prompted by these templates, the layout-aware numbers above are not strictly held out; the naive parser, which carries every other claim, was not changed. A renderer bug that dropped bullet markers from DOCX text boxes (hybrid only) was also fixed.

#### Downstream effects: keyword search vs. knockouts

- **Keyword search barely notices layout.** The mean keyword-score change was between 0.000 and -0.026 for every layout, template and format. Words survive in the raw text even when structure does not.
- **Knockouts notice.** Under a "missing field = reject" policy, the 9 qualified candidate x posting pairs that pass as single column were handled like this:

  | Template | Table PDF | Two-column PDF | Text-box PDF |
  |---|---|---|---|
  | classic | 9 of 9 rejected | 1 of 9 rejected | 0 |
  | latex | 9 of 9 rejected | 9 of 9 rejected | 0 |
  | career_center | 9 of 9 rejected | 9 of 9 rejected | 0 |
  | modern, hybrid | n/a: all 48 pairs rejected even as single column | | |

  Under the gentler "missing field = human review" policy, the same failures mostly send candidates to review instead, which also lets unqualified candidates through the screen (34 REJECT -> REVIEW for classic tables).
- **Single column is necessary, not sufficient.** With the modern and hybrid templates, every candidate was rejected under the strict policy even as a clean single-column PDF, because the degree field could not be read.

### 2. Synonym sensitivity

![Synonym sensitivity](results/synonyms.png)

21 cases across 9 term pairs (posting wording vs. a common alternative, both directions).

| Scorer | Mean score change [95% CI] | Dropped in rank (16-pool) | Dropped in rank (202-pool) |
|---|---|---|---|
| Keyword (exact) | -20% [-24, -16] | 48% | 62% |
| TF-IDF | -16% [-23, -9] | 24% | 29% |
| Embedding (MiniLM) | **-0.3% [-1.3, +0.6]** | 10% | 29% |
| Keyword + taxonomy | 0% | 0% | 0% |

Exact matching is the most brittle: "Onshape" instead of "CAD" cost 30%, "FEA" vs "finite element analysis" 25%. MiniLM's score barely moved for any pair, and a curated alias list fixes keyword matching completely. In the larger pool, even MiniLM's tiny shifts move some resumes, because scores there are tightly packed.

### 3. Keyword-stuffing audit

This is an **audit of weak scoring methods**, not a guide to gaming them. Every attack below is trivially caught by a human reader or by a one-line parser fix, and it misrepresents the candidate.

![Keyword-stuffing audit](results/stuffing.png)

For candidates who started outside the top 5, the share whose stuffed resume outscored the best *unstuffed* resume in the pool:

| Attack | Keyword | TF-IDF | Embedding (MiniLM) |
|---|---|---|---|
| Visible repeated keyword list | 100% | 88% [76, 97] | **0%** |
| Same list in white text | 100% | 88% [76, 97] | **0%** |
| Whole posting pasted in white text | 100% | 100% | **42% [27, 61]** |
| Either hidden attack, parser drops white text | 0% | 0% | 0% |

- Keyword and TF-IDF scorers are fooled by any added keyword list. Repetition specifically inflates TF-IDF (raw term counts); the presence-based keyword scorer is fooled by the first mention.
- MiniLM was never pushed past the best genuine candidate by a keyword list, though it still lifted weak resumes: 79 to 85% of them entered the top 5 in the 16-resume pool, and 30 to 45% in the 202-resume pool. A pasted copy of the posting beat the best genuine resume 42% of the time (48% [32, 62] in the larger pool). "Embeddings resist stuffing" is true for keyword lists, false for pasted postings.
- The effective fix lives in the parser, not the scorer: discarding white or tiny characters before scoring (`parse_resume(..., drop_invisible=True)`) neutralized both hidden attacks for every scorer. Nothing in a scorer can tell a visible keyword list from a real skills section; that is a human-review problem.

### 4. Ranking stability

![Ranking stability, 202-resume pool](results/public_pool/stability.png)

Each of 16 resumes got small wording edits (verb synonyms, reordered bullets, `Jun 2025` -> `06/2025`, one generic "collaborated with cross-functional teams" bullet, all combined) while the rest of the pool stayed fixed. 240 cases per scorer.

| Mean \|rank change\| | Keyword | TF-IDF | Embedding (MiniLM) |
|---|---|---|---|
| 16-resume pool, one generic bullet | 0 | 0.7 | 0.6 |
| 202-resume pool, one generic bullet | 0 | 3.9 | **12.2** (max 34) |
| 202-resume pool, verb synonyms | 0 | 1.1 | 2.7 |
| Top-5 changes, 202-resume pool | 0 | 4 | **7** |

- The keyword scorer never moved: none of the edits touched a skill term.
- **The scorer that best resists synonyms and keyword lists is the least stable ranker.** Mean-pooled embeddings shift with every sentence, so one generic bullet moved MiniLM rankings by 12 positions on average in a realistic pool. That would have been invisible in the 16-resume pool, where the same edit moved resumes less than one position.
- There is no free lunch: exact matching is stable but blind to synonyms; embeddings understand synonyms but react to filler.

## Open-source engines, mixed in

Three open-source projects are run alongside this project's own code. None of their code is stored in this repo: `scripts/setup_external.sh` downloads them, and small adapters in `ats_sim/engines.py` and `external/` run them and map their output into the same schema, using this project's own degree and date normalizers so every engine is scored by the same rules.

| Engine | License | What it is | How it runs here |
|---|---|---|---|
| [OpenResume](https://github.com/xitanggg/open-resume) | AGPL-3.0 | Resume builder whose parser students use to test "ATS readability". Groups text by font features (bold, capitals) rather than a heading list; documented as single-column only | Unmodified source, bundled at run time under Node by `external/openresume/run.mjs` |
| [pyresparser](https://github.com/OmkarPathak/pyresparser) | GPL-3.0 | The most widely used Python resume parser; spaCy 2 + NLTK + a keyword skills list | Isolated Python 3.8 environment, called as a subprocess (`external/pyresparser/run.py`) |
| [SkillNer](https://github.com/AnasAito/SkillNER) | MIT | Skill extraction against the EMSI/Lightcast open skills database (31,278 skills) | Imported directly; used as a fourth scorer |

### Parser benchmark

`scripts/benchmark_parsers.py` runs every parser on all 640 labeled resumes. Because engines format fields differently, scoring is lenient (a school with ", Raleigh, NC" still counts), and fields an engine never attempts are excluded rather than counted as misses (pyresparser has no graduation date or GPA field). The table uses only fields all engines attempt.

![Parser benchmark](results/parsers/parsers.png)

| PDF, all templates | ours, naive | ours, layout-aware | OpenResume | pyresparser | ensemble |
|---|---|---|---|---|---|
| Single column | 0.81 | 0.81 | 0.85 | 0.53 | **0.90** |
| Two column | 0.60 | 0.77 | 0.71 | 0.48 | **0.80** |
| Table | 0.33 | 0.75 | 0.42 | 0.51 | **0.82** |
| Text boxes | 0.53 | 0.80 | 0.68 | 0.51 | **0.81** |

- **OpenResume is the best single parser on clean single-column PDFs**, mainly because it finds experience entries (0.87 vs 0.44 for ours): it detects headings by formatting, so unfamiliar headings and line conventions in the held-out templates hurt it less (hybrid: 0.59 vs 0.33).
- **It breaks on tables (0.42) and degrades on two columns and text boxes**, as its own documentation warns. It also put a sidebar heading ("CONTACT") in the name field on two-column resumes, and glued the contact-icon glyph onto every modern-template email address ("npriya.raman@example.com").
- **pyresparser is weak on this corpus.** It dropped the area code from every phone number, returned no school for any of the 640 resumes, scored 0.03 F1 on experience entries, and its whole-text skill matching returns words like "Design" and "Process". Its reading order handles columns well (it uses pdfminer's layout analysis), which keeps it flat across layouts.
- **Mixing them works.** A field-by-field majority vote across our layout-aware parser, OpenResume and pyresparser (`engines.vote`) is the best or tied-best result in every layout. It keeps OpenResume's experience and skills, and falls back to our reading order where OpenResume breaks. The vote rule is generic, but it was written after seeing these results, so treat the ensemble numbers as in-sample.

Full tables, including per-template and per-field results: `results/parsers/PARSERS.md`.

### SkillNer as a fourth scorer

`run_experiments.py --with-skillner` scores resumes by the share of the posting's SkillNer skills that SkillNer also finds in the resume.

| | Keyword (64 curated skills) | SkillNer (31k skills) | Embedding (MiniLM) |
|---|---|---|---|
| Synonym penalty | -20% | -10% [-15, -6] | -0.3% |
| Fooled by a keyword list (beats best genuine resume) | 100% | 100% | 0% |
| Wording edits that changed rank | 0 | 0 | some |

A big taxonomy halves the synonym penalty (it maps "finite element analysis" to FEA and "SOPs" to SOP) but still misses "ML", "NLP", "GMP" spelled out, "RCA" and "additive manufacturing". It also brings noise: "B.S." matched "B (Programming Language)" and "Co-op" matched "Component Object Model". Being presence-based, it is as easy to stuff as exact matching and as stable under rewording.

## Check your own resume

```bash
python scripts/check_resume.py my_resume.pdf --authorized yes --public-pool data/kaggle/Resume.csv
python scripts/check_resume.py my_resume.pdf --gold my_resume.gold.json   # adds per-parser accuracy
python scripts/check_resume.py my_resume.pdf --posting real_posting.txt   # score against real postings (repeatable)
```

The report (written to `private/`, which is gitignored) shows what each parser extracted side by side, parsing risks (headings a heading-list parser will miss, glyphs that do not map to text, hidden text, detected columns or tables), skills found by the curated list and by SkillNer, the knockout result under each parse, and the resume's score and rank against each posting, including two extra postings in `data/jobs_extra/`. Those two were written while testing a real student resume, so they are not a neutral benchmark for that resume; for a meaningful rank, pass real postings with `--posting`. The report also flags a degree with no extractable field of study and parsers that disagree on the school. An optional answer key in the `data/personas.json` format adds per-parser accuracy. Nothing is uploaded anywhere.

## Limitations

- **Five templates, written by one person who knew the parser.** They cover common real conventions, but they are a convenience sample, not a random draw from real resumes. The pooled intervals resample only four held-out templates, so they understate how much real designs vary.
- **The parser is heuristic on purpose.** The layout-aware mode handles one gutter per page and ruled tables or bordered boxes; it stands in for commercial layout analysis, not a measurement of any product. Its held-out numbers are optimistic after the bug fix described above.
- **Small synthetic answer key.** 16 personas and 3 postings. The public resumes add realism to the ranking pools but have no labels, and they are plain text, so they never test parsing.
- **The answer key and the resumes come from the same source**, so there is no human labeling error. That keeps the F1 numbers clean, but messy real-world inputs (scanned PDFs, ligatures, headers and footers, varied PDF generators) are not tested.
- **Experiments 2 to 4 use the classic single-column PDF** so the scorer is the only moving part; scoring results on other templates may differ.
- **Third-party engines are run, not reimplemented, but through adapters.** The mapping into this project's schema (and the lenient scoring) is a choice; another mapping could move their numbers a few points. Each engine's raw output is cached under `results/_tmp/engine_cache/` for inspection.
- **Scores are not decisions.** Real outcomes depend on recruiters, referrals and timing. Nothing here estimates anyone's chance of getting an interview.
- **Knockout source is a modeling choice.** Knockout flips assume the candidate accepted a parse-prefilled form. If candidates type their answers, layout cannot affect knockouts at all.

## Resume bullet

Suggested wording, using only claims that held across all five templates:

> Engineered a Python ATS simulator that parses, screens and ranks resumes with 3 scoring methods. Across 640 controlled resumes in 5 templates, table layouts cut PDF field-extraction F1 to 0.37 in every template and text boxes cost 25 to 74%, while a layout-aware reader recovered most of the loss; an audit showed hidden keyword stuffing fooled keyword and TF-IDF scoring but not sentence embeddings.

Do not quote "two-column cuts accuracy by 33%". That number came from the development template only; across held-out templates the F1 effect was 4 to 9%. The interesting two-column story is that it barely moves overall accuracy yet can still break the graduation-date and degree fields that knockout rules use, which makes a good interview answer. The embedding stability trade-off (experiment 4) is another.

## Repository layout

```
ats_sim/        parser, jd analyzer, knockouts, scorers, search, pipeline, renderer, experiments
data/           personas (answer key), jobs, skills list, sample PDFs (full corpus is generated)
scripts/        build_corpus.py, run_experiments.py, fetch_public_resumes.py,
                benchmark_parsers.py, check_resume.py, setup_external.sh
external/       runners for OpenResume (Node) and pyresparser (Python 3.8); no third-party code
results/parsers/      parser benchmark (ours vs OpenResume vs pyresparser vs ensemble)
results/        16-resume pool: CSVs, charts, RESULTS.md, summary.json
results/public_pool/  same experiments with 186 public distractor resumes
tests/          pytest suite (forces the LSA backend so it runs offline)
ats_sim/webapp/ the app: FastAPI server and a dependency-free HTML/CSS/JS front end
ats_sim/report.py     resume analysis shared by the app and scripts/check_resume.py
launchers/      double-click launchers for macOS, Windows and Linux
app.py          older Streamlit developer dashboard
.github/        GitHub Actions: tests on every push
```
