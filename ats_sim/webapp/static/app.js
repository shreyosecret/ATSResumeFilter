"use strict";
/* ATS Simulator front end. Plain JS, no dependencies, works offline.
   Every string that comes from a resume or posting goes through esc(). */

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v, d = 0) => (v == null ? "n/a" : `${(v * 100).toFixed(d)}%`);
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

const ICONS = {
  check: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="m9 14 2 2 4-4"/>',
  screen: '<path d="M3 6h18M6 12h12M10 18h4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  research: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  about: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  ok: '<path d="m5 12 4.5 4.5L19 7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  warn: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
  bad: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
};
const icon = (name, size = 18) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch (e) {}
  if (!res.ok) throw new Error((body && body.detail) || `Request failed (${res.status})`);
  return body;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 4200);
}

const SCORER_LABELS = { keyword: "Keyword match", tfidf: "TF-IDF", embedding: "Semantic (AI)", skillner: "SkillNer" };
const SCORER_HELP = {
  keyword: "Share of the posting's terms that appear word for word",
  tfidf: "Word-overlap similarity, weighted by rarity",
  embedding: "Meaning-based similarity from a sentence-embedding model",
  skillner: "Overlap of skills found by SkillNer",
};
const FIELD_LABELS = { name: "Name", email: "Email", phone: "Phone", degree_level: "Degree", field_of_study: "Field of study",
  school: "School", grad_date: "Graduation", gpa: "GPA" };
const FIELDS = Object.keys(FIELD_LABELS);
const KO = {
  PASS: { cls: "good", icon: "ok", label: "Passes screening" },
  REVIEW: { cls: "warn", icon: "warn", label: "Sent to review" },
  REJECT: { cls: "bad", icon: "bad", label: "Screened out" },
};
const koBadge = (status) => { const k = KO[status] || KO.REVIEW; return `<span class="badge ${k.cls}">${icon(k.icon, 13)}${esc(k.label)}</span>`; };
const fmtDate = (iso) => {
  if (!iso) return null;
  const [y, m] = String(iso).split("-");
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m) - 1];
  return mon ? `${mon} ${y}` : iso;
};
const show = (v) => (v == null || v === "" ? '<span class="cell-empty">not found</span>' : esc(v));
const options = (items, selected) => items.map(([v, l]) => `<option value="${esc(v)}"${v === selected ? " selected" : ""}>${esc(l)}</option>`).join("");
const LAYOUT_LABELS = { single: "Single column", two_column: "Two column", table: "Table", textbox: "Text boxes" };
const TEMPLATE_LABELS = { classic: "Classic (dev)", modern: "Modern", latex: "LaTeX student", career_center: "Career center", hybrid: "Hybrid" };

// ------------------------------------------------------------------ app state
const state = { meta: null, ready: false, result: null, file: null };

const ROUTES = [
  { id: "check", label: "Resume check", icon: "check", render: renderCheck },
  { id: "screen", label: "Screening", icon: "screen", render: renderScreen },
  { id: "search", label: "Boolean search", icon: "search", render: renderSearch },
  { id: "research", label: "Research", icon: "research", render: renderResearch },
  { id: "about", label: "About", icon: "about", render: renderAbout },
];

function currentRoute() {
  const id = (location.hash || "#/check").replace("#/", "");
  return ROUTES.find((r) => r.id === id) || ROUTES[0];
}

function renderNav() {
  const route = currentRoute();
  $("#nav").innerHTML = ROUTES.map((r) =>
    `<button class="nav-btn" data-route="${r.id}" ${r.id === route.id ? 'aria-current="page"' : ""}>${icon(r.icon)}<span class="label">${r.label}</span></button>`).join("");
  $("#nav").querySelectorAll(".nav-btn").forEach((b) => b.addEventListener("click", () => { location.hash = `#/${b.dataset.route}`; }));
}

function route() {
  renderNav();
  closeDrawer();
  const r = currentRoute();
  document.title = `${r.label} · ATS Simulator`;
  r.render($("#main"));
  $("#main").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ status + theme
async function pollStatus() {
  let s;
  try { s = await api("/api/status"); } catch (e) { s = { status: "offline", ready: false }; }
  const pill = $("#status");
  const cls = s.ready ? "ready" : s.status === "error" || s.status === "offline" ? "error" : "busy";
  const text = s.ready ? `Ready · pool of ${s.pool}` : s.status === "error" ? "Startup failed" : s.status === "offline" ? "Server stopped" : `Warming up: ${s.status}`;
  pill.innerHTML = `<span class="dot ${cls}"></span><span>${esc(text)}</span>`;
  if (s.status === "error") pill.title = s.error || "";
  if (s.ready && !state.ready) {
    state.ready = true;
    state.meta = await api("/api/meta");
    route();
    return;
  }
  if (!s.ready && s.status !== "error") setTimeout(pollStatus, 1200);
}

function initTheme() {
  const set = (choice) => {
    if (choice === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = choice;
    store.set("ats-theme", choice === "system" ? null : choice);
    document.querySelectorAll("[data-theme-choice]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === choice)));
  };
  document.querySelectorAll("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => set(b.dataset.themeChoice)));
  set(document.documentElement.dataset.theme || "system");
}

function waiting(main, title, sub) {
  main.innerHTML = `<div class="page">${pageHead(title, sub)}<div class="card"><div class="loading"><div class="spinner"></div>
    <div><strong>Getting things ready</strong><div class="muted small">Loading the language model and indexing the comparison resumes. The first launch takes about a minute; later launches take seconds.</div></div></div></div></div>`;
}
const pageHead = (title, sub, right = "") => `<header class="page-head"><div><h1>${title}</h1><p>${sub}</p></div>${right}</header>`;

// ------------------------------------------------------------------ resume check
function renderCheck(main) {
  const title = "Resume check";
  const sub = "See how parsers read your resume, what could trip a screening rule, and how it scores against job postings.";
  if (!state.ready) return waiting(main, title, sub);
  if (state.result) return renderResult(main);
  const m = state.meta;
  const saved = store.get("ats-check", {});
  const engineCount = (m.engines.openresume ? 1 : 0) + (m.engines.pyresparser ? 1 : 0);
  main.innerHTML = `<div class="page">${pageHead(title, sub)}
    <div class="grid-2" style="grid-template-columns: 1.15fr 1fr; align-items: start">
      <div class="card">
        <div class="dropzone" id="dz" tabindex="0" role="button" aria-label="Choose a resume file">
          <div class="dz-icon">${icon("upload", 24)}</div>
          <strong>Drop your resume here</strong>
          <span class="muted">or click to choose a PDF or Word file (up to 10 MB)</span>
          <div id="file-slot"></div>
        </div>
        <input type="file" id="file" accept=".pdf,.docx" hidden>
        <div class="notice" style="margin-top:14px">${icon("lock", 16)}<span>Analyzed on this computer. The file is read, analyzed and deleted; nothing is uploaded or stored.</span></div>
      </div>
      <div class="card stack">
        <label class="field"><span>Compare against</span>
          <select id="posting">${options([["all", "All built-in postings"], ...m.postings.map((p) => [p.id, p.title]), ["paste", "Paste a real posting…"]], saved.posting || "all")}</select>
        </label>
        <label class="field" id="paste-wrap" hidden><span>Posting text</span>
          <textarea id="paste" placeholder="Paste the full job description, including requirements"></textarea>
        </label>
        <div class="grid-2">
          <label class="field"><span>Authorized to work in the US?</span>
            <select id="auth">${options([["unknown", "Not specified"], ["yes", "Yes"], ["no", "No"]], saved.auth || "unknown")}</select></label>
          <label class="field"><span>Need visa sponsorship?</span>
            <select id="spons">${options([["unknown", "Not specified"], ["no", "No"], ["yes", "Yes"]], saved.spons || "unknown")}</select></label>
        </div>
        <label class="switch" title="${engineCount ? "Runs OpenResume and pyresparser too, then combines them" : "Not installed. Run scripts/setup_external.sh"}">
          <input type="checkbox" id="engines" ${engineCount ? "checked" : "disabled"}>
          <span>Compare with open-source parsers ${engineCount ? `<span class="muted">(${engineCount} installed)</span>` : '<span class="muted">(not installed)</span>'}</span></label>
        <label class="switch" title="${m.engines.skillner ? "Matches against 31,000 skills; takes about a minute" : "SkillNer not installed"}">
          <input type="checkbox" id="deep" ${m.engines.skillner ? "" : "disabled"}>
          <span>Deep skill scan <span class="muted">(SkillNer, slower)</span></span></label>
        <button class="btn primary" id="go" disabled>Analyze resume</button>
      </div>
    </div>
    <div id="check-out"></div></div>`;

  const dz = $("#dz"), input = $("#file"), go = $("#go");
  const setFile = (f) => {
    if (!f) return;
    if (!/\.(pdf|docx)$/i.test(f.name)) return toast("Please choose a PDF or DOCX file.");
    state.file = f;
    $("#file-slot").innerHTML = `<span class="file-pill">${icon("file", 15)}${esc(f.name)}</span>`;
    go.disabled = false;
  };
  if (state.file) setFile(state.file);
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
  const posting = $("#posting");
  const syncPaste = () => { $("#paste-wrap").hidden = posting.value !== "paste"; };
  posting.addEventListener("change", syncPaste);
  syncPaste();
  go.addEventListener("click", () => runAnalysis());
}

async function runAnalysis() {
  const posting = $("#posting").value, paste = $("#paste").value;
  if (posting === "paste" && paste.trim().length < 40) return toast("Paste the posting text first.");
  store.set("ats-check", { posting, auth: $("#auth").value, spons: $("#spons").value });
  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("posting_id", posting === "paste" ? "all" : posting);
  fd.append("posting_text", posting === "paste" ? paste : "");
  fd.append("authorized", $("#auth").value);
  fd.append("sponsorship", $("#spons").value);
  fd.append("engines", $("#engines").checked ? "true" : "false");
  fd.append("deep_skills", $("#deep").checked ? "true" : "false");
  const go = $("#go");
  go.disabled = true;
  const steps = ["Reading the file", "Parsing with every parser", "Checking for screening risks", "Scoring against postings", "Ranking against other resumes"];
  if ($("#deep").checked) steps.push("Scanning 31,000 skills (about a minute)");
  let i = 0;
  const out = $("#check-out");
  const paint = () => {
    out.innerHTML = `<div class="card" style="margin-top:16px"><div class="loading"><div class="spinner"></div><div><strong>${esc(steps[Math.min(i, steps.length - 1)])}…</strong>
      <div class="muted small">Step ${Math.min(i + 1, steps.length)} of ${steps.length}</div></div></div></div>`;
  };
  paint();
  const timer = setInterval(() => { i += 1; paint(); }, 1400);
  try {
    state.result = await api("/api/analyze", { method: "POST", body: fd });
    clearInterval(timer);
    renderResult($("#main"));
  } catch (e) {
    clearInterval(timer);
    out.innerHTML = `<div class="notice bad" style="margin-top:16px">${icon("bad", 16)}<span>${esc(e.message)}</span></div>`;
    go.disabled = false;
  }
}

function initials(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
}

function renderResult(main) {
  const r = state.result;
  const best = r.parsers[r.best];
  const risks = r.risks;
  const issues = risks.filter((x) => x.level === "bad" || x.level === "warn");
  const filled = FIELDS.filter((f) => best[f] != null).length;
  const agreeFields = Object.values(r.agreement).filter((a) => a.agree && a.of > 1).length;
  const multi = Object.keys(r.parsers).filter((n) => n !== "ensemble").length > 1;
  const emb = (m) => m.scores.find((s) => s.name === "embedding") || m.scores[m.scores.length - 1];
  const sorted = [...r.matches].sort((a, b) => emb(a).rank - emb(b).rank);
  const top = sorted[0];

  main.innerHTML = `<div class="page">
    ${pageHead("Resume check", `Results for <strong>${esc(r.file)}</strong>`,
      `<button class="btn" id="again">${icon("upload", 16)}Check another</button>`)}
    <div class="card">
      <div class="person">
        <div class="avatar" aria-hidden="true">${esc(initials(best.name))}</div>
        <div><h2>${best.name ? esc(best.name) : '<span class="cell-empty">Name not found</span>'}</h2>
          <div class="meta">${[best.email, best.phone, [best.degree_level, best.field_of_study].filter(Boolean).join(" in "), best.school, fmtDate(best.grad_date) && `Graduating ${fmtDate(best.grad_date)}`]
            .filter(Boolean).map((x) => `<span>${esc(x)}</span>`).join("")}</div></div>
      </div>
    </div>
    <div class="grid-4" style="margin-top:16px">
      ${stat("Fields read", `${filled}<small> / ${FIELDS.length}</small>`, "Contact, education and dates the best parse found")}
      ${stat("Parser agreement", multi ? `${agreeFields}<small> / ${FIELDS.length}</small>` : "n/a", multi ? "Fields every parser read the same way" : "Install the open-source parsers to compare")}
      ${stat("Issues to fix", `${issues.length}`, issues.length ? "See below, worst first" : "Nothing that trips a parser")}
      ${stat("Closest posting", top ? `#${emb(top).rank}<small> of ${emb(top).of}</small>` : "n/a", top ? esc(top.posting.title) : "")}
    </div>

    <div class="grid-2" style="margin-top:16px; align-items:start">
      <section class="card"><div class="card-head"><div><h2>What could trip a parser</h2><div class="card-sub">Worst first. Green items are fine.</div></div></div>
        ${[...risks].sort((a, b) => order(a.level) - order(b.level)).map(riskRow).join("") || '<div class="muted">No risks found.</div>'}
      </section>
      <section class="card"><div class="card-head"><div><h2>Skills found</h2><div class="card-sub">What a skills matcher would tag from the text.</div></div></div>
        <div class="small muted" style="margin-bottom:6px">Curated list (${r.skills.curated.length})</div>
        <div class="chips">${r.skills.curated.map((s) => `<span class="chip hit">${esc(s)}</span>`).join("") || '<span class="muted small">None from the curated list.</span>'}</div>
        ${r.skills.skillner ? `<div class="small muted" style="margin:14px 0 6px">SkillNer, EMSI/Lightcast taxonomy (${r.skills.skillner.length})</div>
          <div class="chips">${r.skills.skillner.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</div>` : ""}
      </section>
    </div>

    <section class="card" style="margin-top:16px">
      <div class="card-head"><div><h2>Against each posting</h2>
        <div class="card-sub">Ranked against ${r.pool.size} other resumes (${r.pool.synthetic} synthetic${r.pool.public ? `, ${r.pool.public} public` : ""}). Screening uses what the parser read, like an uncorrected pre-filled application form.</div></div></div>
      ${sorted.map(matchCard).join("")}
      <div class="legend"><span><i style="background:var(--accent)"></i>Your score</span><span><i class="tick"></i>Best other resume</span><span><i class="tick median"></i>Typical resume (median)</span></div>
    </section>

    <section class="card" style="margin-top:16px">
      <div class="card-head"><div><h2>What each parser read</h2><div class="card-sub">Highlighted cells are fields where parsers read different values.</div></div></div>
      ${parserTable(r)}
    </section>

    <section class="card" style="margin-top:16px">
      <details><summary>Text the simple parser read, in order</summary><pre class="raw" style="margin-top:12px">${esc(r.raw_text)}</pre></details>
    </section>
    <p class="muted small" style="margin-top:18px">A simulator modeled on documented ATS behavior. It does not reproduce or predict any vendor's system.</p>
  </div>`;
  $("#again").addEventListener("click", () => { state.result = null; renderCheck($("#main")); });
}

const order = (lvl) => ({ bad: 0, warn: 1, info: 2, ok: 3 }[lvl] ?? 4);
const stat = (label, value, detail) => `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value">${value}</div><div class="stat-detail">${detail}</div></div>`;
const riskRow = (x) => `<div class="risk"><div class="risk-icon ${x.level}">${icon(x.level, 16)}</div><div><div class="risk-title">${esc(x.title)}</div><div class="risk-detail">${esc(x.detail)}</div></div></div>`;

function meter(s) {
  const clamp = (v) => Math.max(0, Math.min(1, v || 0));
  const scale = Math.max(s.score, s.best_other || 0, 0.0001);
  const norm = (v) => (s.name === "keyword" || s.name === "skillner" ? clamp(v) : clamp(v / (scale * 1.08)));
  const label = SCORER_LABELS[s.name] || s.name;
  return `<div class="meter" title="${esc(SCORER_HELP[s.name] || "")}">
    <div class="meter-name">${esc(label)}<small>${esc(SCORER_HELP[s.name] || "")}</small></div>
    <div class="meter-track" role="img" aria-label="${esc(label)}: ${s.score.toFixed(2)}, rank ${s.rank} of ${s.of}">
      <div class="meter-fill" style="width:${(norm(s.score) * 100).toFixed(1)}%"></div>
      ${s.median_other != null ? `<div class="meter-tick median" style="left:${(norm(s.median_other) * 100).toFixed(1)}%"></div>` : ""}
      ${s.best_other != null ? `<div class="meter-tick" style="left:${(norm(s.best_other) * 100).toFixed(1)}%"></div>` : ""}
    </div>
    <div class="meter-val"><strong>#${s.rank}</strong> <span class="muted">of ${s.of}</span></div>
  </div>`;
}

function matchCard(m) {
  const kos = Object.entries(m.knockouts);
  const ko = kos.length ? kos[kos.length - 1][1] : null;
  const why = ko ? [...ko.reasons, ...ko.missing.map((x) => `missing ${x}`)] : [];
  const reqTerms = new Set(m.requirements.filter((q) => q.level === "required").map((q) => q.term.toLowerCase()));
  const chip = (t, cls) => `<span class="chip ${cls}${t.split(" / ").some((x) => reqTerms.has(x.toLowerCase())) ? " req" : ""}">${esc(t)} </span>`;
  return `<div class="match card" style="box-shadow:none">
    <div class="match-head"><div><h3>${esc(m.posting.title)}</h3>
      ${ko && m.posting.has_knockouts ? `<div class="ko-reasons">${why.length ? esc(why.join("; ")) : "Meets every screening rule."}</div>` : '<div class="ko-reasons">No screening rules for this posting.</div>'}</div>
      ${ko && m.posting.has_knockouts ? koBadge(ko.status) : '<span class="badge neutral">No knockouts</span>'}</div>
    <div style="margin-top:10px">${m.scores.map(meter).join("")}</div>
    <div class="grid-2" style="margin-top:10px">
      <div><div class="small muted" style="margin-bottom:6px">Posting terms you have</div><div class="chips">${m.matched.map((t) => chip(t, "hit")).join("") || '<span class="muted small">None found word for word.</span>'}</div></div>
      <div><div class="small muted" style="margin-bottom:6px">Not found word for word</div><div class="chips">${m.missing.map((t) => chip(t, "miss")).join("") || '<span class="muted small">Nothing missing.</span>'}</div></div>
    </div></div>`;
}

function parserTable(r) {
  const names = Object.keys(r.parsers);
  const label = (n) => esc(r.parser_labels[n] || n);
  const rows = FIELDS.map((f) => {
    const a = r.agreement[f];
    const diff = a && a.filled >= 2 && !a.agree;
    return `<tr><th scope="row" style="text-transform:none;font-size:13px;color:var(--text-2);position:static">${FIELD_LABELS[f]}</th>${names.map((n) => {
      const v = f === "grad_date" ? fmtDate(r.parsers[n][f]) : r.parsers[n][f];
      return `<td class="${diff ? "diff" : ""}">${show(v)}</td>`;
    }).join("")}</tr>`;
  });
  rows.push(`<tr><th scope="row" style="text-transform:none;font-size:13px;color:var(--text-2);position:static">Jobs found</th>${names.map((n) => `<td>${r.parsers[n].experience.length}</td>`).join("")}</tr>`);
  rows.push(`<tr><th scope="row" style="text-transform:none;font-size:13px;color:var(--text-2);position:static">Skills listed</th>${names.map((n) => `<td>${r.parsers[n].skills.length}</td>`).join("")}</tr>`);
  return `<div class="table-wrap"><table class="data"><thead><tr><th>Field</th>${names.map((n) => `<th>${label(n)}${n === r.best ? ' <span class="badge info" style="margin-left:4px">used</span>' : ""}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

// ------------------------------------------------------------------ screening
function screenControls(prefix, s, withPosting = true) {
  const m = state.meta;
  return `<div class="controls">
    ${withPosting ? `<label class="field"><span>Job posting</span><select id="${prefix}-posting">${options(m.postings.map((p) => [p.id, p.title]), s.posting)}</select></label>` : ""}
    <label class="field"><span>Resume template</span><select id="${prefix}-template">${options(m.templates.map((t) => [t, TEMPLATE_LABELS[t] || t]), s.template)}</select></label>
    <label class="field"><span>Layout</span><select id="${prefix}-layout">${options(m.layouts.map((l) => [l, LAYOUT_LABELS[l] || l]), s.layout)}</select></label>
    <label class="field"><span>File format</span><select id="${prefix}-format">${options(m.formats.map((f) => [f, f.toUpperCase()]), s.format)}</select></label>
    <label class="field"><span>Parser</span><select id="${prefix}-parser">${options([["naive", "Simple"], ["layout_aware", "Layout-aware"]], s.parser)}</select></label>
  </div>`;
}

function readControls(prefix, keys) {
  const out = {};
  keys.forEach((k) => { const el = $(`#${prefix}-${k}`); if (el) out[k] = el.type === "checkbox" ? el.checked : el.value; });
  return out;
}

function renderScreen(main) {
  const title = "Screening";
  const sub = "The recruiter's view: 16 fictional candidates screened and ranked for a posting. Change the template, layout or parser and watch who drops out.";
  if (!state.ready) return waiting(main, title, sub);
  const m = state.meta;
  const s = Object.assign({ posting: m.postings[0].id, template: "classic", layout: "single", format: "pdf", parser: "naive", policy: "review", rank_by: "embedding" }, store.get("ats-screen", {}));
  main.innerHTML = `<div class="page">${pageHead(title, sub)}
    <div class="card">${screenControls("sc", s)}
      <div class="controls" style="margin-top:12px">
        <label class="field"><span>If a screening field can't be read</span><select id="sc-policy">${options([["review", "Send to a human"], ["reject", "Reject automatically"], ["pass", "Let it through"]], s.policy)}</select></label>
        <label class="field"><span>Rank by</span><select id="sc-rank_by">${options(["keyword", "tfidf", "embedding"].map((k) => [k, SCORER_LABELS[k]]), s.rank_by)}</select></label>
      </div></div>
    <div id="sc-out" style="margin-top:16px"></div></div>`;
  const keys = ["posting", "template", "layout", "format", "parser", "policy", "rank_by"];
  const load = async () => {
    const q = readControls("sc", keys);
    store.set("ats-screen", q);
    const out = $("#sc-out");
    out.innerHTML = `<div class="card"><div class="skeleton" style="width:40%"></div><div class="skeleton" style="margin-top:12px"></div><div class="skeleton" style="margin-top:12px;width:80%"></div></div>`;
    try {
      const data = await api(`/api/screen?${new URLSearchParams(q)}`);
      renderScreenTable(out, data, q);
    } catch (e) { out.innerHTML = `<div class="notice bad">${icon("bad", 16)}<span>${esc(e.message)}</span></div>`; }
  };
  keys.forEach((k) => $(`#sc-${k}`).addEventListener("change", load));
  load();
}

function renderScreenTable(out, data, q) {
  const counts = { PASS: 0, REVIEW: 0, REJECT: 0 };
  data.rows.forEach((r) => { counts[r.knockout] = (counts[r.knockout] || 0) + 1; });
  const max = Object.fromEntries(data.scorers.map((n) => [n, Math.max(...data.rows.map((r) => r.scores[n]), 0.0001)]));
  out.innerHTML = `<div class="grid-4" style="margin-bottom:16px">
      ${stat("Candidates", data.rows.length, esc(data.posting.title))}
      ${stat("Pass screening", counts.PASS, "Meet every knockout rule")}
      ${stat("Sent to review", counts.REVIEW, "A screening field could not be read")}
      ${stat("Screened out", counts.REJECT, "Failed a knockout rule")}
    </div>
    <div class="table-wrap"><table class="data"><thead><tr>
      <th class="num">Rank</th><th>Candidate</th><th>Screening</th>${data.scorers.map((n) => `<th>${esc(SCORER_LABELS[n] || n)}</th>`).join("")}
    </tr></thead><tbody>
    ${data.rows.map((r) => {
      const rank = r.ranks[q.rank_by];
      const why = [r.reasons, r.missing && `missing ${r.missing}`].filter(Boolean).join("; ");
      return `<tr class="clickable" data-id="${esc(r.id)}" tabindex="0">
        <td class="num"><strong>${rank == null ? "–" : rank}</strong></td>
        <td class="name-cell"><strong>${r.name ? esc(r.name) : '<span class="cell-empty">name not read</span>'}</strong><span>${esc(r.intent)}</span></td>
        <td title="${esc(why)}">${koBadge(r.knockout)}</td>
        ${data.scorers.map((n) => `<td style="min-width:140px"><div class="row" style="gap:8px;flex-wrap:nowrap"><div class="meter-track" style="flex:1;height:8px"><div class="meter-fill" style="width:${(r.scores[n] / max[n] * 100).toFixed(1)}%"></div></div><span class="small" style="width:38px;text-align:right;font-variant-numeric:tabular-nums">${r.scores[n].toFixed(2)}</span></div></td>`).join("")}
      </tr>`;
    }).join("")}</tbody></table></div>
    <p class="muted small" style="margin-top:10px">Scores are only comparable within a column. Bars are scaled to the top candidate. Click a row to see what the parser read.</p>`;
  out.querySelectorAll("tr.clickable").forEach((tr) => {
    const open = () => openCandidate(tr.dataset.id, q);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
  });
}

async function openCandidate(id, q) {
  const d = $("#drawer");
  d.innerHTML = `<div class="loading"><div class="spinner"></div><span>Loading…</span></div>`;
  d.classList.add("open"); d.setAttribute("aria-hidden", "false"); $("#drawer-backdrop").classList.add("open");
  try {
    const c = await api(`/api/candidate/${encodeURIComponent(id)}?${new URLSearchParams({ template: q.template, layout: q.layout, format: q.format, parser: q.parser })}`);
    const norm = (v) => String(v ?? "").toLowerCase().replace(/[^a-z0-9@.]+/g, " ").trim();
    const same = (f) => (f === "phone" ? String(c.parsed[f] || "").replace(/\D/g, "").slice(-10) === String(c.truth[f] || "").replace(/\D/g, "").slice(-10)
      : f === "gpa" ? (c.parsed[f] == null && c.truth[f] == null) || Number(c.parsed[f]) === Number(c.truth[f]) : norm(c.parsed[f]) === norm(c.truth[f]));
    const truthSkills = new Set(c.skills.truth.map(norm));
    d.innerHTML = `<div class="card-head"><div><h2 style="font-size:19px">${esc(c.truth.name)}</h2><div class="card-sub">${esc(c.intent)}</div></div>
        <button class="btn ghost" id="close-drawer" aria-label="Close">${icon("close")}</button></div>
      <div class="row" style="margin-bottom:16px"><span class="badge neutral">${esc(TEMPLATE_LABELS[q.template] || q.template)}</span><span class="badge neutral">${esc(LAYOUT_LABELS[q.layout])}</span><span class="badge neutral">${esc(q.format.toUpperCase())}</span>
        ${q.format === "pdf" ? `<a class="btn" style="height:30px;margin-left:auto" href="/api/sample/${encodeURIComponent(id)}?template=${encodeURIComponent(q.template)}&layout=${encodeURIComponent(q.layout)}" target="_blank" rel="noopener">${icon("external", 14)}Open PDF</a>` : ""}</div>
      <h3 style="font-size:14px;margin-bottom:8px">Parsed vs. what the resume says</h3>
      <div class="table-wrap"><table class="data"><thead><tr><th>Field</th><th>Parser read</th><th>Resume says</th><th></th></tr></thead><tbody>
        ${FIELDS.map((f) => { const ok = same(f); return `<tr><td class="muted">${FIELD_LABELS[f]}</td><td>${show(f === "grad_date" ? fmtDate(c.parsed[f]) : c.parsed[f])}</td><td>${show(f === "grad_date" ? fmtDate(c.truth[f]) : c.truth[f])}</td>
          <td>${ok ? `<span class="check-ok" aria-label="correct">${icon("ok", 16)}</span>` : `<span class="check-bad" aria-label="wrong">${icon("bad", 16)}</span>`}</td></tr>`; }).join("")}
      </tbody></table></div>
      <h3 style="font-size:14px;margin:18px 0 8px">Skills the parser listed</h3>
      <div class="chips">${c.skills.parsed.map((s) => `<span class="chip ${truthSkills.has(norm(s)) ? "hit" : ""}">${esc(s)}</span>`).join("") || '<span class="muted small">No skills section found.</span>'}</div>
      <h3 style="font-size:14px;margin:18px 0 8px">Jobs the parser found</h3>
      <div class="chips">${c.experience.parsed.map((s) => `<span class="chip">${esc(s)}</span>`).join("") || '<span class="muted small">None.</span>'}</div>
      <details style="margin-top:18px"><summary>Text the parser read, in order</summary><pre class="raw" style="margin-top:10px">${esc(c.raw_text)}</pre></details>`;
    $("#close-drawer").addEventListener("click", closeDrawer);
    $("#close-drawer").focus();
  } catch (e) { d.innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
}

function closeDrawer() {
  $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); $("#drawer-backdrop").classList.remove("open");
}

// ------------------------------------------------------------------ search
function renderSearch(main) {
  const title = "Boolean search";
  const sub = "How recruiters actually find candidates: keyword queries with AND, OR, NOT, quotes and parentheses.";
  if (!state.ready) return waiting(main, title, sub);
  const s = Object.assign({ q: '(Python OR MATLAB) AND "GMP"', k: "10", synonyms: false, template: "classic", layout: "single", format: "pdf", parser: "naive" }, store.get("ats-search", {}));
  const examples = ['(Python OR MATLAB) AND "GMP"', '"machine learning" NOT marketing', "CAD AND (FEA OR ANSYS)", "ML", "SQL AND Python AND -intern"];
  main.innerHTML = `<div class="page">${pageHead(title, sub)}
    <div class="card">
      <div class="row" style="flex-wrap:nowrap"><input type="search" id="se-q" value="${esc(s.q)}" aria-label="Query" style="flex:1;height:44px;font-size:15px" placeholder='e.g. (Python OR MATLAB) AND "GMP"'>
        <button class="btn primary" id="se-go" style="height:44px">${icon("search", 16)}Search</button></div>
      <div class="row" style="margin-top:12px"><span class="small muted">Try:</span>${examples.map((e) => `<button class="chip" data-ex="${esc(e)}" style="cursor:pointer">${esc(e)}</button>`).join("")}</div>
      <div style="margin-top:14px">${screenControls("se", s, false)}</div>
      <div class="row" style="margin-top:12px"><label class="switch"><input type="checkbox" id="se-synonyms" ${s.synonyms ? "checked" : ""}><span>Expand synonyms <span class="muted">("ML" also finds "machine learning")</span></span></label></div>
    </div>
    <div id="se-out" style="margin-top:16px"></div></div>`;
  const run = async () => {
    const q = Object.assign(readControls("se", ["q", "template", "layout", "format", "parser", "synonyms"]), { k: "16" });
    store.set("ats-search", q);
    const out = $("#se-out");
    try {
      const data = await api(`/api/search?${new URLSearchParams(q)}`);
      out.innerHTML = data.hits.length ? `<div class="card"><div class="card-head"><h2>${data.hits.length} match${data.hits.length === 1 ? "" : "es"}</h2><span class="muted small">Ranked by how often the terms appear</span></div>
        ${data.hits.map((h, i) => `<div class="risk"><div class="risk-icon info" style="font-weight:700">${i + 1}</div><div><div class="risk-title">${esc(h.name)} <span class="muted small" style="font-weight:400">· ${esc(h.intent)}</span></div>
          <div class="chips" style="margin-top:6px">${Object.entries(h.terms).map(([t, n]) => `<span class="chip ${n ? "hit" : "miss"}">${esc(t)} × ${n}</span>`).join("")}</div></div></div>`).join("")}</div>`
        : `<div class="card empty">${icon("search", 32)}<p><strong>No candidates match.</strong><br>Exact matching is strict: try synonyms, or fewer AND terms.</p></div>`;
    } catch (e) { out.innerHTML = `<div class="notice bad">${icon("bad", 16)}<span>${esc(e.message)}</span></div>`; }
  };
  $("#se-go").addEventListener("click", run);
  $("#se-q").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  main.querySelectorAll("[data-ex]").forEach((b) => b.addEventListener("click", () => { $("#se-q").value = b.dataset.ex; run(); }));
  ["template", "layout", "format", "parser", "synonyms"].forEach((k) => $(`#se-${k}`).addEventListener("change", run));
  run();
}

// ------------------------------------------------------------------ research
async function renderResearch(main) {
  const title = "Research";
  const sub = "What the experiments found: 640 controlled resumes, five templates, four layouts, three open-source engines.";
  main.innerHTML = `<div class="page">${pageHead(title, sub)}<div id="rs-out"><div class="card"><div class="skeleton"></div></div></div></div>`;
  try {
    const d = await api("/api/research");
    const out = $("#rs-out");
    if (!d.available) { out.innerHTML = `<div class="card empty"><p>No results yet. Run <code>python scripts/run_experiments.py</code>.</p></div>`; return; }
    out.innerHTML = `<div class="grid-4">${d.stats.map((s) => stat(esc(s.label), s.format === "pct" ? `${s.value.toFixed(0)}<small>%</small>` : s.value.toFixed(2), esc(s.detail))).join("")}</div>
      <div class="grid-2 research-grid" style="margin-top:16px">${d.charts.map((c) => `<figure class="card chart-card" style="margin:0"><div class="card-head"><div><h3>${esc(c.title)}</h3><div class="card-sub">${esc(c.caption)}</div></div></div>
        <a href="${esc(c.src)}" target="_blank" rel="noopener"><img src="${esc(c.src)}" alt="${esc(c.title)}: ${esc(c.caption)}" loading="lazy"></a></figure>`).join("")}</div>
      <p class="muted small" style="margin-top:14px">Charts come from the committed results. Full tables and methods are in the README and results/RESULTS.md.</p>`;
  } catch (e) { $("#rs-out").innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; }
}

// ------------------------------------------------------------------ about
function renderAbout(main) {
  const m = state.meta;
  main.innerHTML = `<div class="page">${pageHead("About", "What this app does, and what it does not claim.")}
    <div class="grid-2" style="align-items:start">
      <div class="card prose">
        <h3 style="margin-top:0">What it models</h3>
        <p>Real applicant tracking systems mostly do three things: turn a resume into fields, screen out applicants on knockout questions (work authorization, graduation date, GPA, degree), and let recruiters search and rank by keywords, sometimes with an AI match score. This app simulates those three stages.</p>
        <p>There is no single magic score that rejects people. Scores only order candidates who pass the knockout rules, and a person decides what happens next.</p>
        <h3>What it does not claim</h3>
        <p>Commercial systems are proprietary. This is a simulator modeled on documented behavior, not a reproduction of Workday, Greenhouse, Lever, iCIMS or any other product.</p>
        <h3>Privacy</h3>
        <p>Everything runs on this computer. Uploaded resumes are read, analyzed and deleted; nothing is sent anywhere.</p>
      </div>
      <div class="card prose">
        <h3 style="margin-top:0">Components</h3>
        <ul>
          <li>Parsers: a simple text-order parser and a layout-aware one (this project)${m ? `, plus ${m.engines.openresume ? "OpenResume (AGPL-3.0)" : "OpenResume (not installed)"} and ${m.engines.pyresparser ? "pyresparser (GPL-3.0)" : "pyresparser (not installed)"}, run as separate programs` : ""}.</li>
          <li>Scorers: exact keyword match, TF-IDF, and sentence embeddings (${m ? esc(m.embedding_backend || "unavailable") : "…"})${m && m.engines.skillner ? ", plus SkillNer (MIT) for skills" : ""}.</li>
          <li>Comparison pool: ${m ? `${m.pool.synthetic} fictional candidates${m.pool.public ? ` and ${m.pool.public} public resumes (CC0)` : ""}` : "…"}.</li>
        </ul>
        <h3>Version</h3><p>${m ? esc(m.version) : ""}</p>
      </div>
    </div></div>`;
}

// ------------------------------------------------------------------ boot
$("#drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
window.addEventListener("hashchange", route);
initTheme();
route();
pollStatus();
