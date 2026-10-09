"use strict";
/* ATS Simulator front end. Plain JS, no dependencies, works offline.
   Every string that comes from a resume or posting goes through esc(). */

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

const ICONS = {
  check: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="m9 14 2 2 4-4"/>',
  screen: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  research: '<path d="M3 3v18h18"/><path d="M7 16v-4M12 16V8M17 16v-7"/>',
  about: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  upload: '<path d="M12 15V3M7 8l5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  ok: '<path d="m5 12 4.5 4.5L19 7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  warn: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  bad: '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  external: '<path d="M15 3h6v6M21 3l-9 9"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
  cap: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/>',
  cal: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  parse: '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
  filter: '<path d="M22 3H2l8 9.5V19l4 2v-8.5z"/>',
  rank: '<path d="M8 21V11M16 21V5M12 21v-6"/>',
  table: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>',
  learn: '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/>',
  reset: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
};
const icon = (name, size = 16) =>
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

const SCORERS = {
  keyword: { label: "Keyword match", help: "Share of the posting's terms that appear word for word" },
  tfidf: { label: "TF-IDF", help: "Word-overlap similarity, weighted by how rare each word is" },
  embedding: { label: "Semantic", help: "Meaning-based similarity from a sentence-embedding model" },
  skillner: { label: "SkillNer", help: "Overlap of skills found by SkillNer" },
};
const FIELD_LABELS = { name: "Name", email: "Email", phone: "Phone", degree_level: "Degree", field_of_study: "Field of study",
  school: "School", grad_date: "Graduation", gpa: "GPA" };
const FIELDS = Object.keys(FIELD_LABELS);
const KO = {
  PASS: { cls: "good", label: "Passes screening" },
  REVIEW: { cls: "warn", label: "Needs review" },
  REJECT: { cls: "bad", label: "Screened out" },
};
const koBadge = (status) => { const k = KO[status] || KO.REVIEW; return `<span class="badge ${k.cls}"><span class="dot"></span>${esc(k.label)}</span>`; };
const fmtDate = (iso) => {
  if (!iso) return null;
  const [y, m] = String(iso).split("-");
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m) - 1];
  return mon ? `${mon} ${y}` : iso;
};
const show = (v) => (v == null || v === "" ? '<span class="cell-empty">Not found</span>' : esc(v));
const options = (items, selected) => items.map(([v, l]) => `<option value="${esc(v)}"${v === selected ? " selected" : ""}>${esc(l)}</option>`).join("");
const LAYOUT_LABELS = { single: "Single column", two_column: "Two column", table: "Table", textbox: "Text boxes" };
const TEMPLATE_LABELS = { classic: "Classic (dev)", modern: "Modern", latex: "LaTeX student", career_center: "Career center", hybrid: "Hybrid" };
const LEVEL_LABEL = { bad: "Problem", warn: "Warning", info: "Note", ok: "Passed" };
const order = (lvl) => ({ bad: 0, warn: 1, info: 2, ok: 3 }[lvl] ?? 4);

// ------------------------------------------------------------------ shell
const state = { meta: null, ready: false, result: null, file: null, tab: "overview" };

const ROUTES = [
  { id: "check", label: "Resume check", icon: "check", section: "Analyze", render: renderCheck,
    title: "Resume check", sub: "How parsers read a resume, what could trip screening, and how it ranks" },
  { id: "screen", label: "Screening", icon: "screen", section: "Explore", render: renderScreen,
    title: "Screening", sub: "The recruiter's view of 16 fictional candidates" },
  { id: "search", label: "Boolean search", icon: "search", section: "Explore", render: renderSearch,
    title: "Boolean search", sub: "Keyword queries the way recruiters write them" },
  { id: "research", label: "Research", icon: "research", section: "Explore", render: renderResearch,
    title: "Research", sub: "What the controlled experiments revealed" },
  { id: "about", label: "About", icon: "about", section: "Info", render: renderAbout,
    title: "About", sub: "What this app models, and what it does not claim" },
];

function currentRoute() {
  const id = (location.hash || "#/check").replace("#/", "");
  return ROUTES.find((r) => r.id === id) || ROUTES[0];
}

function renderNav() {
  const current = currentRoute();
  let html = "", section = null;
  for (const r of ROUTES) {
    if (r.section !== section) { section = r.section; html += `<div class="nav-section">${section}</div>`; }
    html += `<button class="nav-btn" data-route="${r.id}" ${r.id === current.id ? 'aria-current="page"' : ""}>${icon(r.icon, 17)}<span class="label">${r.label}</span></button>`;
  }
  $("#nav").innerHTML = html;
  $$(".nav-btn", $("#nav")).forEach((b) => b.addEventListener("click", () => { location.hash = `#/${b.dataset.route}`; }));
}

function setHeader(title, sub, actions = "") {
  $("#page-title").textContent = title;
  $("#page-sub").textContent = sub;
  $("#page-actions").innerHTML = actions;
}

function route() {
  renderNav();
  closeDrawer();
  hideTip();
  const r = currentRoute();
  document.title = `${r.title} · ATS Simulator`;
  setHeader(r.title, r.sub);
  r.render($("#main"));
  $("#main").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

async function pollStatus() {
  let s;
  try { s = await api("/api/status"); } catch (e) { s = { status: "offline", ready: false }; }
  const chip = $("#status");
  const cls = s.ready ? "ready" : s.status === "error" || s.status === "offline" ? "error" : "busy";
  const text = s.ready ? "Ready" : s.status === "error" ? "Startup failed" : s.status === "offline" ? "Server stopped" : "Warming up";
  chip.innerHTML = `<span class="dot ${cls}"></span><span>${esc(text)}</span>`;
  chip.title = s.ready ? `Comparison pool: ${s.pool} resumes. Semantic model: ${s.embedding_backend}` : (s.error || s.status);
  if (s.ready && !state.ready) {
    state.ready = true;
    setInterval(() => { fetch("/api/status").catch(() => {}); }, 30000); // keep-alive while the page is open
    state.meta = await api("/api/meta");
    $("#version").textContent = `Version ${state.meta.version}`;
    route();
    api("/api/update").then((u) => { // does nothing online unless turned on in About
      if (u.enabled && u.newer) toast(`Version ${u.latest} of ATS Simulator is available. See About to download it.`);
    }).catch(() => {});
    return;
  }
  if (!s.ready && s.status !== "error") setTimeout(pollStatus, 1200);
}

function initTheme() {
  const set = (choice) => {
    if (choice === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = choice;
    store.set("ats-theme", choice === "system" ? null : choice);
    $$("[data-theme-choice]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === choice)));
  };
  $$("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => set(b.dataset.themeChoice)));
  set(document.documentElement.dataset.theme || "system");
}

function waiting(main) {
  main.innerHTML = `<div class="page"><div class="card"><div class="loading"><div class="spinner"></div>
    <div><div style="font-weight:600">Preparing the analysis engine</div>
    <div class="muted small">Loading the language model and indexing the comparison resumes. The first launch takes about a minute; later launches take seconds.</div></div></div></div></div>`;
}

const stat = (label, value, detail) =>
  `<div class="card stat"><div class="stat-label">${label}</div><div class="stat-value">${value}</div><div class="stat-detail">${detail}</div></div>`;

// ------------------------------------------------------------------ resume check: upload
function renderCheck(main) {
  if (!state.ready) return waiting(main);
  if (state.result) return renderResult(main);
  const m = state.meta;
  const saved = store.get("ats-check", {});
  const mode = state.jobMode || saved.mode || "paste";
  const engineCount = (m.engines.openresume ? 1 : 0) + (m.engines.pyresparser ? 1 : 0);
  main.innerHTML = `<div class="page">
    <section class="card">
      <div class="card-head"><div><h2>Analyze a resume</h2><div class="sub">PDF or Word, up to 10 MB</div></div></div>
      <div class="upload">
        <div class="upload-left">
          <div class="dropzone" id="dz" tabindex="0" role="button" aria-label="Choose a resume file">
            <div class="dz-icon">${icon("upload", 20)}</div>
            <strong>Drag and drop your resume</strong>
            <div class="dz-or">or <b>browse files</b></div>
            <div id="file-slot"></div>
          </div>
          <input type="file" id="file" accept=".pdf,.docx" hidden>
        </div>
        <div class="upload-right">
          <div class="field"><span>Job to score against</span>
            <div class="seg seg-wide" role="tablist" aria-label="Job to score against">
              <button type="button" data-mode="paste" aria-selected="${mode === "paste"}">Paste a job description</button>
              <button type="button" data-mode="builtin" aria-selected="${mode === "builtin"}">Sample postings</button>
            </div></div>
          <div id="paste-wrap" ${mode === "paste" ? "" : "hidden"}>
            <label class="field"><span>Job title <span class="hint">Optional</span></span>
              <input type="text" id="paste-title" placeholder="For example: Data Analyst Intern" value="${esc(state.pasteTitle || "")}"></label>
            <label class="field" style="margin-top:12px"><span>Job description <span class="hint" id="paste-count"></span></span>
              <textarea id="paste" rows="10" placeholder="Copy the whole posting from the job site and paste it here: the duties, the requirements and the preferred qualifications. Screening rules such as degree, GPA, graduation date and work authorization are read from it.">${esc(state.pasteText || "")}</textarea></label>
          </div>
          <label class="field" id="builtin-wrap" ${mode === "builtin" ? "" : "hidden"}><span>Sample postings</span>
            <select id="posting">${options([["all", `All sample postings (${m.postings.length})`], ...m.postings.map((p) => [p.id, p.title])], saved.posting && saved.posting !== "paste" ? saved.posting : "all")}</select>
          </label>
          <div class="grid g2" style="gap:14px">
            <label class="field"><span>Authorized to work in the US</span>
              <select id="auth">${options([["unknown", "Not specified"], ["yes", "Yes"], ["no", "No"]], saved.auth || "unknown")}</select></label>
            <label class="field"><span>Needs visa sponsorship</span>
              <select id="spons">${options([["unknown", "Not specified"], ["no", "No"], ["yes", "Yes"]], saved.spons || "unknown")}</select></label>
          </div>
          <div class="divider" style="margin:4px 0"></div>
          <label class="switch"><input type="checkbox" id="engines" ${engineCount ? "checked" : "disabled"}>
            <span class="switch-text">Compare with open-source parsers<small>${engineCount ? `OpenResume and pyresparser, combined by vote (${engineCount} installed)` : "Not installed. Run scripts/setup_external.sh to enable."}</small></span></label>
          <label class="switch"><input type="checkbox" id="deep" ${m.engines.skillner ? "" : "disabled"}>
            <span class="switch-text">Deep skill scan<small>${m.engines.skillner ? "SkillNer, 31,000 skills. Adds about a minute." : "SkillNer is not installed."}</small></span></label>
        </div>
      </div>
      <div class="card-foot">
        <span class="row muted small">${icon("lock", 14)}Processed on this computer. The file is deleted after analysis.</span>
        <button class="btn primary lg" id="go" disabled>Analyze resume</button>
      </div>
    </section>
    <div id="check-out"></div>
    <section class="card steps-card">
      <div class="steps">
        ${[["Parse", "Up to four parsers turn the file into fields: contact, education, experience and skills."],
           ["Screen", "Knockout rules check graduation date, GPA, degree field and work authorization."],
           ["Rank", "Three scorers compare the resume with each posting and rank it against hundreds of others."]]
          .map(([t, d], i) => `<div class="step"><div class="step-num">${i + 1}</div><div><h3>${t}</h3><p>${d}</p></div></div>`).join("")}
      </div>
    </section>
  </div>`;

  const dz = $("#dz"), input = $("#file"), go = $("#go");
  const setFile = (f) => {
    if (!f) return;
    if (!/\.(pdf|docx)$/i.test(f.name)) return toast("Please choose a PDF or DOCX file.");
    state.file = f;
    const kb = f.size / 1024;
    $("#file-slot").innerHTML = `<span class="file-pill">${icon("file", 15)}<span>${esc(f.name)}</span><small>${kb > 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.round(kb) + " KB"}</small></span>`;
    go.disabled = false;
  };
  if (state.file) setFile(state.file);
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
  $$("[data-mode]").forEach((b) => b.addEventListener("click", () => {
    state.jobMode = b.dataset.mode;
    $$("[data-mode]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    $("#paste-wrap").hidden = state.jobMode !== "paste";
    $("#builtin-wrap").hidden = state.jobMode !== "builtin";
    if (state.jobMode === "paste") $("#paste").focus();
  }));
  const paste = $("#paste"), count = () => {
    const n = paste.value.trim().split(/\s+/).filter(Boolean).length;
    $("#paste-count").textContent = n ? `${n} words` : "";
  };
  paste.addEventListener("input", () => { state.pasteText = paste.value; count(); });
  $("#paste-title").addEventListener("input", (e) => { state.pasteTitle = e.target.value; });
  count();
  go.addEventListener("click", runAnalysis);
}

async function runAnalysis() {
  const mode = state.jobMode || (($("#paste-wrap").hidden) ? "builtin" : "paste");
  const posting = $("#posting").value, paste = $("#paste").value;
  if (mode === "paste" && paste.trim().split(/\s+/).length < 20) {
    $("#paste").focus();
    return toast("Paste the job description first (at least a few sentences), or choose Sample postings.");
  }
  store.set("ats-check", { mode, posting, auth: $("#auth").value, spons: $("#spons").value });
  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("posting_id", mode === "paste" ? "all" : posting);
  fd.append("posting_text", mode === "paste" ? paste : "");
  fd.append("posting_title", mode === "paste" ? $("#paste-title").value : "");
  fd.append("authorized", $("#auth").value);
  fd.append("sponsorship", $("#spons").value);
  fd.append("engines", $("#engines").checked ? "true" : "false");
  fd.append("deep_skills", $("#deep").checked ? "true" : "false");
  const go = $("#go");
  go.disabled = true;
  go.innerHTML = `<span class="spinner" style="width:16px;height:16px;border-width:2px;border-color:rgba(255,255,255,.35);border-top-color:#fff"></span>Analyzing`;
  const steps = ["Reading the file", "Parsing with every parser", "Checking for screening risks",
    ...(state.meta && state.meta.engines.visual ? ["Reading the page the way a person sees it"] : []),
    mode === "paste" ? "Reading the job description's rules" : "Scoring against postings", "Ranking against other resumes"];
  if ($("#deep").checked) steps.push("Scanning 31,000 skills");
  let i = 0;
  const out = $("#check-out");
  const paint = () => {
    const k = Math.min(i, steps.length - 1);
    out.innerHTML = `<div class="card"><div class="loading"><div class="spinner"></div><div style="flex:1"><div style="font-weight:600">${esc(steps[k])}…</div>
      <div class="muted small">Step ${k + 1} of ${steps.length}</div><div class="progress"><div style="width:${Math.round(((k + 1) / (steps.length + 1)) * 100)}%"></div></div></div></div></div>`;
  };
  paint();
  const timer = setInterval(() => { i += 1; paint(); }, 1300);
  try {
    state.result = await api("/api/analyze", { method: "POST", body: fd });
    state.tab = "overview";
    clearInterval(timer);
    renderResult($("#main"));
  } catch (e) {
    clearInterval(timer);
    out.innerHTML = `<div class="notice bad">${icon("bad")}<span>${esc(e.message)}</span></div>`;
    go.disabled = false;
    go.textContent = "Analyze resume";
  }
}

// ------------------------------------------------------------------ resume check: results
const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
const scoreOf = (m, name) => m.scores.find((s) => s.name === name);
const primary = (m) => scoreOf(m, "embedding") || m.scores[m.scores.length - 1];
const topPct = (s) => Math.max(1, Math.round((s.rank / s.of) * 100));

function renderResult(main) {
  const r = state.result;
  const best = r.parsers[r.best];
  const counts = { bad: 0, warn: 0, info: 0, ok: 0 };
  r.risks.forEach((x) => { counts[x.level] = (counts[x.level] || 0) + 1; });
  const filled = FIELDS.filter((f) => best[f] != null).length;
  const multi = Object.keys(r.parsers).filter((n) => n !== "ensemble").length > 1;
  const agree = Object.values(r.agreement).filter((a) => a.agree && a.filled > 1).length;
  const sorted = [...r.matches].sort((a, b) => primary(a).rank - primary(b).rank);
  const top = sorted[0];
  setHeader("Resume check", r.file, `${r.report_md ? `<button class="btn" id="report">${icon("download")}Download report</button>` : ""}<button class="btn" id="again">${icon("upload")}New analysis</button>`);
  $("#again").addEventListener("click", () => { state.result = null; route(); });
  if (r.report_md) $("#report").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([r.report_md], { type: "text/markdown" }));
    a.download = `${(r.file || "resume").replace(/\.[^.]+$/, "")} ATS report.md`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast("Report saved to your downloads folder.");
  });

  const degree = [best.degree_level, best.field_of_study].filter(Boolean).join(", ");
  main.innerHTML = `<div class="page">
    <section class="card person">
      <div class="avatar" aria-hidden="true">${esc(initials(best.name))}</div>
      <div style="min-width:0">
        <h2>${best.name ? esc(best.name) : '<span class="cell-empty">Name not found</span>'}</h2>
        <div class="person-meta">
          ${best.email ? `<span>${icon("mail", 14)}${esc(best.email)}</span>` : ""}
          ${best.phone ? `<span>${icon("phone", 14)}${esc(best.phone)}</span>` : ""}
          ${degree || best.school ? `<span>${icon("cap", 14)}${esc([degree, best.school].filter(Boolean).join(" · "))}</span>` : ""}
          ${best.grad_date ? `<span>${icon("cal", 14)}Graduating ${esc(fmtDate(best.grad_date))}</span>` : ""}
        </div>
      </div>
      <div class="person-right">
        ${counts.bad ? `<span class="badge bad"><span class="dot"></span>${counts.bad} problem${counts.bad > 1 ? "s" : ""}</span>` : ""}
        ${counts.warn ? `<span class="badge warn"><span class="dot"></span>${counts.warn} warning${counts.warn > 1 ? "s" : ""}</span>` : ""}
        <span class="badge good"><span class="dot"></span>${counts.ok} passed</span>
      </div>
    </section>
    ${r.matches.length === 1 ? jobMatchCard(r.matches[0]) : ""}
    <div class="grid g4">
      ${stat("Fields extracted", `${filled}<small> / ${FIELDS.length}</small>`, "Contact, education and dates read by the best parse")}
      ${stat("Parser agreement", multi ? `${agree}<small> / ${FIELDS.length}</small>` : "–", multi ? "Fields every parser read identically" : "Install the open-source parsers to compare")}
      ${stat("Issues to fix", `${counts.bad + counts.warn}`, counts.bad + counts.warn ? `${counts.bad} problem${counts.bad === 1 ? "" : "s"}, ${counts.warn} warning${counts.warn === 1 ? "" : "s"}` : "Nothing that trips a parser")}
      ${stat("Best semantic match", top ? `Top ${topPct(primary(top))}<small>%</small>` : "–", top ? esc(top.posting.title) : "")}
    </div>
    <section class="card">
      <div class="tabs" role="tablist">
        ${[["overview", "Overview"], ["matches", "Job matches", r.matches.length], ["parsers", "Parser comparison", Object.keys(r.parsers).length], ["text", "Extracted text"], ...(r.lines || r.model_pending ? [["learn", "Teach the model"]] : [])]
          .map(([id, label, n]) => `<button class="tab" role="tab" data-tab="${id}" aria-selected="${state.tab === id}">${label}${n != null ? `<span class="count">${n}</span>` : ""}</button>`).join("")}
      </div>
      <div id="tab-body"></div>
    </section>
    <p class="muted small">A simulator modeled on documented ATS behavior. It does not reproduce or predict any vendor's system.</p>
  </div>`;
  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    state.tab = t.dataset.tab;
    $$(".tab").forEach((x) => x.setAttribute("aria-selected", String(x === t)));
    renderTab();
  }));
  renderTab();
}

function renderTab() {
  const r = state.result, body = $("#tab-body");
  if (state.tab === "overview") {
    const risks = [...r.risks].sort((a, b) => order(a.level) - order(b.level));
    body.innerHTML = `<div class="grid g-main" style="gap:0">
      <div style="border-right:1px solid var(--border)">
        <div class="card-head" style="border-bottom:1px solid var(--border)"><div><h2>Parsing checks</h2><div class="sub">Worst first</div></div></div>
        ${risks.map((x) => `<div class="issue"><div class="issue-icon ${x.level}">${icon(x.level === "ok" ? "ok" : x.level, 16)}</div>
          <div><div class="issue-title">${esc(x.title)}${x.level !== "ok" ? `<span class="badge ${x.level === "bad" ? "bad" : x.level === "warn" ? "warn" : "info"}" style="height:20px;font-size:11px">${LEVEL_LABEL[x.level]}</span>` : ""}</div>
          <div class="issue-detail">${esc(x.detail)}</div></div></div>`).join("")}
      </div>
      <div>
        <div class="card-head"><div><h2>Skills found</h2><div class="sub">What a skills matcher would tag</div></div></div>
        <div class="card-body">
          <div class="label" style="margin-bottom:8px">Curated list · ${r.skills.curated.length}</div>
          <div class="tags">${r.skills.curated.map((s) => `<span class="tag hit">${esc(s)}</span>`).join("") || '<span class="muted small">None from the curated list.</span>'}</div>
          ${r.skills.skillner ? `<div class="label" style="margin:18px 0 8px">SkillNer taxonomy · ${r.skills.skillner.length}</div>
            <div class="tags">${r.skills.skillner.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>` : ""}
          <div class="divider"></div>
          <div class="label" style="margin-bottom:8px">Comparison pool</div>
          <div class="small muted">Ranked against ${r.pool.size} resumes: ${r.pool.synthetic} fictional candidates${r.pool.public ? ` and ${r.pool.public} public resumes` : ""}.</div>
        </div>
      </div></div>`;
  } else if (state.tab === "matches") {
    const sorted = [...r.matches].sort((a, b) => primary(a).rank - primary(b).rank);
    const scorers = sorted[0] ? sorted[0].scores.map((s) => s.name) : [];
    body.innerHTML = `<div class="table-wrap"><table class="data"><thead><tr>
        <th>Posting</th><th>Screening</th>${scorers.map((n) => `<th title="${esc(SCORERS[n] ? SCORERS[n].help : "")}">${esc(SCORERS[n] ? SCORERS[n].label : n)}</th>`).join("")}<th></th>
      </tr></thead><tbody>
      ${sorted.map((m, i) => {
        const ko = Object.values(m.knockouts).pop();
        const why = ko ? [...ko.reasons, ...ko.missing.map((x) => `missing ${x}`)].join("; ") : "";
        return `<tr class="clickable" data-i="${i}" tabindex="0" aria-expanded="false">
          <td><div class="cell-title">${esc(m.posting.title)}</div><div class="cell-sub">${m.posting.has_knockouts ? esc(why || "Meets every screening rule") : "No screening rules"}</div></td>
          <td>${m.posting.has_knockouts && ko ? koBadge(ko.status) : '<span class="badge neutral">Not screened</span>'}</td>
          ${m.scores.map((s) => `<td>${pctlCell(s)}</td>`).join("")}
          <td class="num"><span class="chev">${icon("chevron")}</span></td></tr>
          <tr class="detail" data-for="${i}" hidden><td colspan="${3 + m.scores.length}">${matchDetail(m)}</td></tr>`;
      }).join("")}</tbody></table></div>
      <div class="chart-foot" style="padding:12px 20px">Percentiles compare this resume with ${r.pool.size} others for each posting. Top 1% is best. Click a row for details.</div>`;
    $$("tr.clickable", body).forEach((tr) => {
      const toggle = () => {
        const d = $(`tr.detail[data-for="${tr.dataset.i}"]`, body);
        const open = d.hidden;
        d.hidden = !open;
        tr.classList.toggle("expanded", open);
        tr.setAttribute("aria-expanded", String(open));
      };
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    });
  } else if (state.tab === "parsers") {
    body.innerHTML = parserTable(r);
  } else if (state.tab === "learn" && !r.lines) {
    body.innerHTML = `<div class="card-body"><div class="notice">${icon("info")}<span>The learned parser is still getting ready (${esc(r.model_pending)}). This happens once; analyze the resume again in a minute to label and teach it.</span></div></div>`;
  } else if (state.tab === "learn") {
    renderLearn(body);
  } else {
    body.innerHTML = `<div class="card-body"><div class="label" style="margin-bottom:10px">Text in the order the simple parser read it</div><pre class="raw">${esc(r.raw_text)}</pre></div>`;
  }
}

// ------------------------------------------------------------------ resume check: teaching
const LINE_LABELS = { name: "Name", contact: "Contact", heading: "Heading", summary: "Summary", education: "Education",
  experience: "Experience", projects: "Projects", skills: "Skills", other: "Other" };
const UNSURE = 0.8;

function renderLearn(body) {
  const r = state.result;
  if (!r.edits) r.edits = r.lines.map((x) => x.label);
  const model = r.model || {};
  const unsure = r.lines.filter((x) => x.confidence < UNSURE).length;
  const changed = r.edits.filter((y, i) => y !== r.lines[i].label).length;
  const onlyUnsure = !!state.onlyUnsure;
  const labelOpts = Object.keys(LINE_LABELS);
  body.innerHTML = `<div class="card-body">
      <div class="learn-head">
        <div class="prose" style="max-width:640px"><p style="margin:0">The <strong>learned parser</strong> is a small neural network that labels every line with the section it belongs to. Fix any wrong labels below, then <strong>Confirm and teach</strong>: the network updates on this computer and reads the next resume with what it learned. It learns where sections are, never whether a candidate is good.</p></div>
        <dl class="kv learn-kv">
          <dt>Resumes taught here</dt><dd class="tnum">${model.taught ?? 0}</dd>
          <dt>Training lines</dt><dd class="tnum">${model.lines_seen ?? "–"}</dd>
          <dt>Unsure on this resume</dt><dd class="tnum">${unsure} of ${r.lines.length}</dd>
        </dl>
      </div>
      <div class="learn-bar">
        <label class="switch"><input type="checkbox" id="only-unsure" ${onlyUnsure ? "checked" : ""}><span><span class="small">Show only unsure lines</span></span></label>
        <span class="small muted" id="changed-count">${changed} label${changed === 1 ? "" : "s"} changed</span>
        <span style="flex:1"></span>
        <button class="btn ghost sm" id="model-reset" title="Forget everything taught on this computer">${icon("reset", 15)}Reset model</button>
        <button class="btn sm" id="export-labels" title="Save these labels, with contact details masked, to share for research">${icon("download", 15)}Export labels</button>
        <button class="btn primary" id="teach">${icon("learn", 16)}Confirm and teach</button>
      </div>
    </div>
    <div class="table-wrap"><table class="data lines"><thead><tr><th class="num">#</th><th>Line</th><th>Section</th><th class="num">Confidence</th></tr></thead><tbody>
      ${r.lines.map((x, i) => (onlyUnsure && x.confidence >= UNSURE && r.edits[i] === x.label) ? "" : `<tr class="${r.edits[i] !== x.label ? "edited" : ""}">
        <td class="num muted tnum">${i + 1}</td>
        <td class="line-text">${esc(x.text)}</td>
        <td><select class="line-label lbl-${esc(r.edits[i])}" data-i="${i}" aria-label="Section for line ${i + 1}">${labelOpts.map((k) => `<option value="${k}" ${k === r.edits[i] ? "selected" : ""}>${LINE_LABELS[k]}</option>`).join("")}</select></td>
        <td class="num tnum ${x.confidence < UNSURE ? "unsure" : "muted"}">${Math.round(x.confidence * 100)}%</td></tr>`).join("")}
      ${onlyUnsure && !r.lines.some((x, i) => x.confidence < UNSURE || r.edits[i] !== x.label) ? `<tr><td colspan="4" class="muted" style="text-align:center;padding:28px">The network is at least ${UNSURE * 100}% sure of every line. Turn the filter off to review them all.</td></tr>` : ""}
    </tbody></table></div>
    <div class="chart-foot" style="padding:12px 20px">Saved only on this computer${model.location ? ` (${esc(model.location)})` : ""}. Reset deletes everything taught here and returns to the starting model.</div>`;
  $$(".line-label", body).forEach((sel) => sel.addEventListener("change", () => {
    const i = +sel.dataset.i;
    r.edits[i] = sel.value;
    sel.className = `line-label lbl-${sel.value}`;
    sel.closest("tr").classList.toggle("edited", sel.value !== r.lines[i].label);
    const n = r.edits.filter((y, j) => y !== r.lines[j].label).length;
    $("#changed-count").textContent = `${n} label${n === 1 ? "" : "s"} changed`;
  }));
  $("#only-unsure").addEventListener("change", (e) => { state.onlyUnsure = e.target.checked; renderLearn(body); });
  $("#teach").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const out = await api("/api/learn", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lines: r.lines.map((x) => x.text), labels: r.edits,
          ...(r.lines.every((x) => x.geo) ? { geo: r.lines.map((x) => x.geo) } : {}) }) });
      const ev = out.event;
      r.lines = out.lines; r.model = out.model; r.edits = null;
      if (out.learned && r.parsers.learned) r.parsers.learned = out.learned;
      toast(`Learned from this resume. You changed ${ev.changed ?? 0} label${ev.changed === 1 ? "" : "s"}; it now labels ${Math.round(ev.accuracy_after * 100)}% of this resume the way you did. The Learned column in Parser comparison is updated.`);
      renderLearn(body);
    } catch (err) { toast(err.message); btn.disabled = false; }
  });
  $("#export-labels").addEventListener("click", async () => {
    if (!confirm("Save this resume's lines and your labels to a file?\n\nYour name, email, phone numbers and links are replaced with placeholders. The rest of the text stays, because the labels describe it. Nothing is sent anywhere: you choose whether to share the file (for example with the project, to test the parser on real resumes).")) return;
    try {
      const out = await api("/api/corrections/export", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lines: r.lines.map((x) => x.text), labels: r.edits,
          ...(r.lines.every((x) => x.geo) ? { geo: r.lines.map((x) => x.geo) } : {}) }) });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], { type: "application/json" }));
      a.download = "resume labels (masked).json";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      toast(`Saved to your downloads folder, with ${out.masked} contact detail${out.masked === 1 ? "" : "s"} masked. Open it to check before sharing.`);
    } catch (err) { toast(err.message); }
  });
  $("#model-reset").addEventListener("click", async () => {
    if (!confirm("Forget everything taught on this computer and go back to the starting model?")) return;
    try {
      const out = await api("/api/model/reset", { method: "POST" });
      r.model = out.model;
      toast("The model was reset. Analyze again to see the starting model's labels.");
      renderLearn(body);
    } catch (err) { toast(err.message); }
  });
}

// ------------------------------------------------------------------ resume check: one job
const RULE_STATUS = { pass: ["ok", "Meets it"], fail: ["bad", "Fails it"], missing: ["warn", "Not found on resume"],
  ask: ["info", "Answer on the form"], info: ["info", "Not used as a rule"] };

function jobMatchCard(m) {
  const ko = Object.values(m.knockouts).pop();
  const status = !m.posting.has_knockouts ? '<span class="badge neutral">No screening rules found</span>' : koBadge(ko.status);
  const req = m.requirements.filter((q) => q.level === "required").map((q) => q.term.toLowerCase());
  const isReq = (t) => t.split(" / ").some((x) => req.includes(x.toLowerCase()));
  const found = { req: m.matched.filter(isReq), pref: m.matched.filter((t) => !isReq(t)) };
  const miss = { req: m.missing.filter(isReq), pref: m.missing.filter((t) => !isReq(t)) };
  const src = {};
  (m.posting.rules_found || []).forEach((x) => { src[{ degree: "Degree", field: "Field of study", gpa: "GPA", graduation: "Graduation", authorization: "Work authorization", sponsorship: "Visa sponsorship" }[x.rule]] = x.source; });
  const rows = (m.rule_checks || []).map((c) => {
    const [ic, label] = RULE_STATUS[c.status] || ["info", c.status];
    return `<tr><td>${esc(c.rule)}</td><td ${src[c.rule] ? `title="From the posting: ${esc(src[c.rule])}"` : ""}>${esc(c.requirement)}${src[c.rule] ? ` <span class="muted">${icon("info", 12)}</span>` : ""}</td>
      <td>${c.resume ? esc(c.rule === "Graduation" ? fmtDate(c.resume) : c.resume) : '<span class="cell-empty">–</span>'}</td>
      <td><span class="rule-status ${c.status}">${icon(ic, 14)}${label}</span></td></tr>`;
  }).join("");
  const tags = (list, cls) => list.map((t) => `<span class="tag ${cls}">${esc(t)}</span>`).join("") || '<span class="muted small">None</span>';
  const scoreRows = m.scores.map((x) => `<div class="score-row"><div><div style="font-weight:500">${esc(SCORERS[x.name] ? SCORERS[x.name].label : x.name)}</div>
      <div class="small muted">${esc(SCORERS[x.name] ? SCORERS[x.name].help : "")}</div></div>
      <div style="text-align:right"><div class="big">Top ${topPct(x)}<small>%</small></div><div class="small muted tnum">score ${x.score.toFixed(2)} · #${x.rank} of ${x.of}</div></div></div>`).join("");
  return `<section class="card">
    <div class="card-head match-head"><div><h2>Match for this job</h2><div class="sub">${esc(m.posting.title)}</div></div>${status}</div>
    <div class="match-grid">
      <div>
        <div class="label" style="margin-bottom:8px">Screening rules read from the posting</div>
        ${rows ? `<div class="table-wrap"><table class="data rules"><thead><tr><th>Rule</th><th>The posting asks</th><th>Your resume</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
          <p class="small muted" style="margin:10px 0 0">Hover a rule to see the sentence it was read from. Many systems ask these as form questions and prefill the answers from the parsed resume; "Not found" is what an uncorrected prefill would leave blank.</p>`
          : '<div class="notice">' + icon("info") + "<span>No degree, GPA, graduation or work-authorization rules were found in the text, so only the scores below apply.</span></div>"}
        <div class="terms-head"><div class="label">Required terms found · ${found.req.length} of ${found.req.length + miss.req.length}</div></div>
        <div class="tags">${tags(found.req, "hit")}</div>
        <div class="terms-head"><div class="label">Required terms not found word for word · ${miss.req.length}</div></div>
        <div class="tags">${tags(miss.req, "miss")}</div>
        <div class="terms-head"><div class="label">Preferred terms · ${found.pref.length} of ${found.pref.length + miss.pref.length} found</div></div>
        <div class="tags">${tags(found.pref, "hit")}${miss.pref.length ? tags(miss.pref, "miss") : ""}</div>
        ${miss.req.length ? `<p class="small muted" style="margin:12px 0 0">Add a missing term only where it is true and you can talk about it; a person reads the resume after the system does.</p>` : ""}
      </div>
      <div>
        <div class="label" style="margin-bottom:4px">How it scores</div>
        ${scoreRows}
        <p class="small muted" style="margin:10px 0 0">Ranks compare your resume with the ${m.scores[0] ? m.scores[0].of - 1 : 0} others in the comparison pool for this same posting. Top 1% is best.</p>
      </div>
    </div></section>`;
}

function pctlCell(s) {
  const fill = s.of > 1 ? 1 - (s.rank - 1) / (s.of - 1) : 1;
  return `<div class="pctl" title="Rank ${s.rank} of ${s.of}. Score ${s.score.toFixed(3)}">
    <div class="pctl-top"><span class="rank">Top ${topPct(s)}<small>%</small></span><span class="small muted tnum">#${s.rank}</span></div>
    <div class="bar-track"><div class="bar-fill" style="width:${(fill * 100).toFixed(1)}%"></div></div></div>`;
}

function matchDetail(m) {
  const req = new Set(m.requirements.filter((q) => q.level === "required").map((q) => q.term.toLowerCase()));
  const tag = (t, cls) => `<span class="tag ${cls}">${esc(t)}${t.split(" / ").some((x) => req.has(x.toLowerCase())) ? '<span class="req">Req</span>' : ""}</span>`;
  return `<div style="padding:4px 0 8px">
    <div class="score-grid">${m.scores.map((s) => `<div class="score-box"><div class="k">${esc(SCORERS[s.name] ? SCORERS[s.name].label : s.name)}</div>
      <div class="v">${s.score.toFixed(2)} <small>rank ${s.rank} of ${s.of}</small></div>
      <div class="note">Typical resume ${s.median_other != null ? s.median_other.toFixed(2) : "–"} · best other ${s.best_other != null ? s.best_other.toFixed(2) : "–"}</div></div>`).join("")}</div>
    <div class="grid g2" style="margin-top:16px;gap:16px">
      <div><div class="label" style="margin-bottom:8px">Posting terms found · ${m.matched.length}</div><div class="tags">${m.matched.map((t) => tag(t, "hit")).join("") || '<span class="muted small">None word for word.</span>'}</div></div>
      <div><div class="label" style="margin-bottom:8px">Not found word for word · ${m.missing.length}</div><div class="tags">${m.missing.map((t) => tag(t, "miss")).join("") || '<span class="muted small">Nothing missing.</span>'}</div></div>
    </div></div>`;
}

function parserTable(r) {
  const names = Object.keys(r.parsers);
  const rows = FIELDS.map((f) => {
    const a = r.agreement[f];
    const diff = a && a.filled >= 2 && !a.agree;
    return `<tr><td class="cell-title" style="font-weight:500">${FIELD_LABELS[f]}${diff ? ' <span class="badge warn" style="height:20px;font-size:11px;margin-left:6px">Differs</span>' : ""}</td>${names.map((n) => {
      const v = f === "grad_date" ? fmtDate(r.parsers[n][f]) : r.parsers[n][f];
      return `<td class="${diff ? "diff" : ""}">${show(v)}</td>`;
    }).join("")}</tr>`;
  });
  rows.push(`<tr><td class="cell-title" style="font-weight:500">Jobs found</td>${names.map((n) => `<td class="tnum">${r.parsers[n].experience.length}</td>`).join("")}</tr>`);
  rows.push(`<tr><td class="cell-title" style="font-weight:500">Skills listed</td>${names.map((n) => `<td class="tnum">${r.parsers[n].skills.length}</td>`).join("")}</tr>`);
  return `<div class="table-wrap"><table class="data"><thead><tr><th>Field</th>${names.map((n) => `<th>${esc(r.parser_labels[n] || n)}${n === r.best ? ' <span class="badge info" style="height:18px;font-size:10.5px;margin-left:4px">Used</span>' : ""}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

// ------------------------------------------------------------------ screening
function filterBar(prefix, s, withPosting = true) {
  const m = state.meta;
  return `${withPosting ? `<label class="field" style="grid-column: span 2"><span>Job posting</span><select id="${prefix}-posting">${options(m.postings.map((p) => [p.id, p.title]), s.posting)}</select></label>` : ""}
    <label class="field"><span>Template</span><select id="${prefix}-template">${options(m.templates.map((t) => [t, TEMPLATE_LABELS[t] || t]), s.template)}</select></label>
    <label class="field"><span>Layout</span><select id="${prefix}-layout">${options(m.layouts.map((l) => [l, LAYOUT_LABELS[l] || l]), s.layout)}</select></label>
    <label class="field"><span>Format</span><select id="${prefix}-format">${options(m.formats.map((f) => [f, f.toUpperCase()]), s.format)}</select></label>
    <label class="field"><span>Parser</span><select id="${prefix}-parser">${options([["naive", "Simple"], ["layout_aware", "Layout-aware"]], s.parser)}</select></label>`;
}
function readControls(prefix, keys) {
  const out = {};
  keys.forEach((k) => { const el = $(`#${prefix}-${k}`); if (el) out[k] = el.type === "checkbox" ? el.checked : el.value; });
  return out;
}

function renderScreen(main) {
  if (!state.ready) return waiting(main);
  const m = state.meta;
  const s = Object.assign({ posting: m.postings[0].id, template: "classic", layout: "single", format: "pdf", parser: "naive", policy: "review", rank_by: "embedding" }, store.get("ats-screen", {}));
  main.innerHTML = `<div class="page">
    <section class="card"><div class="card-body"><div class="toolbar">${filterBar("sc", s)}
      <label class="field"><span>Unreadable field</span><select id="sc-policy">${options([["review", "Send to review"], ["reject", "Reject"], ["pass", "Let through"]], s.policy)}</select></label>
      <label class="field"><span>Rank by</span><select id="sc-rank_by">${options(["keyword", "tfidf", "embedding"].map((k) => [k, SCORERS[k].label]), s.rank_by)}</select></label>
    </div></div></section>
    <div id="sc-out"></div></div>`;
  const keys = ["posting", "template", "layout", "format", "parser", "policy", "rank_by"];
  const load = async () => {
    const q = readControls("sc", keys);
    store.set("ats-screen", q);
    const out = $("#sc-out");
    out.innerHTML = `<div class="card card-body"><div class="skeleton" style="width:40%"></div><div class="skeleton" style="margin-top:14px"></div><div class="skeleton" style="margin-top:14px;width:80%"></div></div>`;
    try { renderScreenTable(out, await api(`/api/screen?${new URLSearchParams(q)}`), q); }
    catch (e) { out.innerHTML = `<div class="notice bad">${icon("bad")}<span>${esc(e.message)}</span></div>`; }
  };
  keys.forEach((k) => $(`#sc-${k}`).addEventListener("change", load));
  load();
}

function renderScreenTable(out, data, q) {
  const counts = { PASS: 0, REVIEW: 0, REJECT: 0 };
  data.rows.forEach((r) => { counts[r.knockout] = (counts[r.knockout] || 0) + 1; });
  const max = Object.fromEntries(data.scorers.map((n) => [n, Math.max(...data.rows.map((r) => r.scores[n]), 0.0001)]));
  out.innerHTML = `<div class="grid g4">
      ${stat("Candidates", data.rows.length, esc(data.posting.title))}
      ${stat(`<span class="dot ready" style="box-shadow:none"></span>Pass screening`, counts.PASS, "Meet every knockout rule")}
      ${stat(`<span class="dot busy" style="animation:none"></span>Needs review`, counts.REVIEW, "A screening field could not be read")}
      ${stat(`<span class="dot error"></span>Screened out`, counts.REJECT, "Failed a knockout rule")}
    </div>
    <section class="card" style="margin-top:20px">
      <div class="card-head"><div><h2>Ranked candidates</h2><div class="sub">Ranked by ${esc(SCORERS[q.rank_by].label.toLowerCase())} among those not screened out. Click a row for details.</div></div></div>
      <div class="table-wrap"><table class="data"><thead><tr>
        <th class="num" style="width:56px">Rank</th><th>Candidate</th><th>Screening</th>${data.scorers.map((n) => `<th>${esc(SCORERS[n].label)}</th>`).join("")}<th></th>
      </tr></thead><tbody>
      ${data.rows.map((r) => {
        const rank = r.ranks[q.rank_by];
        const why = [r.reasons, r.missing && `missing ${r.missing}`].filter(Boolean).join("; ");
        return `<tr class="clickable" data-id="${esc(r.id)}" tabindex="0">
          <td class="num"><span class="rank">${rank == null ? '<span class="cell-empty">–</span>' : rank}</span></td>
          <td><div class="cell-title">${r.name ? esc(r.name) : '<span class="cell-empty">Name not read</span>'}</div><div class="cell-sub">${esc(r.intent)}</div></td>
          <td title="${esc(why)}">${koBadge(r.knockout)}</td>
          ${data.scorers.map((n) => `<td><div class="bar"><div class="bar-track"><div class="bar-fill" style="width:${(r.scores[n] / max[n] * 100).toFixed(1)}%"></div></div><span class="bar-val">${r.scores[n].toFixed(2)}</span></div></td>`).join("")}
          <td class="num"><span class="chev">${icon("chevron")}</span></td></tr>`;
      }).join("")}</tbody></table></div>
      <div class="chart-foot" style="padding:12px 20px">Scores are comparable only within a column; bars are scaled to the top candidate.</div>
    </section>`;
  $$("tr.clickable", out).forEach((tr) => {
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
    const correct = FIELDS.filter(same).length;
    const truthSkills = new Set(c.skills.truth.map(norm));
    d.innerHTML = `<div class="drawer-head"><div><h2>${esc(c.truth.name)}</h2><div class="muted small" style="margin-top:2px">${esc(c.intent)}</div>
        <div class="row" style="margin-top:10px;gap:6px"><span class="badge neutral">${esc(TEMPLATE_LABELS[q.template] || q.template)}</span><span class="badge neutral">${esc(LAYOUT_LABELS[q.layout])}</span><span class="badge neutral">${esc(q.format.toUpperCase())}</span>
        <span class="badge ${correct === FIELDS.length ? "good" : correct >= 6 ? "warn" : "bad"}">${correct} of ${FIELDS.length} fields correct</span></div></div>
        <div class="row" style="flex-wrap:nowrap">${q.format === "pdf" ? `<a class="btn sm" href="/api/sample/${encodeURIComponent(id)}?template=${encodeURIComponent(q.template)}&layout=${encodeURIComponent(q.layout)}" target="_blank" rel="noopener">${icon("external", 14)}PDF</a>` : ""}
        <button class="btn ghost sm" id="close-drawer" aria-label="Close">${icon("close")}</button></div></div>
      <div class="drawer-body">
        <h3>Parsed fields vs. the resume</h3>
        <div class="card"><div class="table-wrap"><table class="data"><thead><tr><th>Field</th><th>Parser read</th><th>Resume says</th><th></th></tr></thead><tbody>
          ${FIELDS.map((f) => { const ok = same(f); return `<tr><td class="muted">${FIELD_LABELS[f]}</td><td>${show(f === "grad_date" ? fmtDate(c.parsed[f]) : c.parsed[f])}</td><td>${show(f === "grad_date" ? fmtDate(c.truth[f]) : c.truth[f])}</td>
            <td class="num">${ok ? `<span class="ok-mark" title="Correct">${icon("ok")}</span>` : `<span class="bad-mark" title="Wrong or missing">${icon("bad")}</span>`}</td></tr>`; }).join("")}
        </tbody></table></div></div>
        <h3>Skills the parser listed</h3>
        <div class="tags">${c.skills.parsed.map((s) => `<span class="tag ${truthSkills.has(norm(s)) ? "hit" : ""}">${esc(s)}</span>`).join("") || '<span class="muted small">No skills section found.</span>'}</div>
        <h3>Jobs the parser found</h3>
        <div class="tags">${c.experience.parsed.map((s) => `<span class="tag">${esc(s)}</span>`).join("") || '<span class="muted small">None.</span>'}</div>
        <h3>Text the parser read, in order</h3>
        <pre class="raw">${esc(c.raw_text)}</pre>
      </div>`;
    $("#close-drawer").addEventListener("click", closeDrawer);
    $("#close-drawer").focus();
  } catch (e) { d.innerHTML = `<div class="drawer-body"><div class="notice bad">${icon("bad")}<span>${esc(e.message)}</span></div></div>`; }
}

function closeDrawer() {
  $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); $("#drawer-backdrop").classList.remove("open");
}

// ------------------------------------------------------------------ search
function renderSearch(main) {
  if (!state.ready) return waiting(main);
  const s = Object.assign({ q: '(Python OR MATLAB) AND "GMP"', synonyms: false, template: "classic", layout: "single", format: "pdf", parser: "naive" }, store.get("ats-search", {}));
  const examples = ['(Python OR MATLAB) AND "GMP"', '"machine learning" NOT marketing', "CAD AND (FEA OR ANSYS)", "ML", "SQL AND Python"];
  main.innerHTML = `<div class="page">
    <section class="card"><div class="card-body">
      <div class="row" style="flex-wrap:nowrap"><div style="position:relative;flex:1"><span style="position:absolute;left:12px;top:12px;color:var(--muted)">${icon("search", 18)}</span>
        <input type="search" id="se-q" value="${esc(s.q)}" aria-label="Query" style="height:44px;padding-left:40px;font-size:15px" placeholder='e.g. (Python OR MATLAB) AND "GMP"'></div>
        <button class="btn primary lg" id="se-go" style="height:44px">Search</button></div>
      <div class="row" style="margin-top:12px;gap:6px"><span class="small muted" style="margin-right:4px">Examples</span>${examples.map((e) => `<button class="tag" data-ex="${esc(e)}" style="cursor:pointer">${esc(e)}</button>`).join("")}</div>
      <div class="divider"></div>
      <div class="toolbar">${filterBar("se", s, false)}
        <div class="field"><span>Synonyms</span><label class="switch" style="height:38px;align-items:center"><input type="checkbox" id="se-synonyms" ${s.synonyms ? "checked" : ""}><span class="switch-text" style="font-weight:400">Expand ("ML" finds "machine learning")</span></label></div>
      </div>
    </div></section>
    <div id="se-out"></div></div>`;
  const run = async () => {
    const q = Object.assign(readControls("se", ["q", "template", "layout", "format", "parser", "synonyms"]), { k: "16" });
    store.set("ats-search", q);
    const out = $("#se-out");
    try {
      const data = await api(`/api/search?${new URLSearchParams(q)}`);
      out.innerHTML = data.hits.length ? `<section class="card"><div class="card-head"><div><h2>${data.hits.length} matching candidate${data.hits.length === 1 ? "" : "s"}</h2><div class="sub">Ranked by how often the query terms appear</div></div></div>
        <div class="table-wrap"><table class="data"><thead><tr><th class="num" style="width:56px">#</th><th>Candidate</th><th>Term hits</th><th class="num">Score</th></tr></thead><tbody>
        ${data.hits.map((h, i) => `<tr><td class="num"><span class="rank">${i + 1}</span></td><td><div class="cell-title">${esc(h.name)}</div><div class="cell-sub">${esc(h.intent)}</div></td>
          <td><div class="tags">${Object.entries(h.terms).map(([t, n]) => `<span class="tag ${n ? "hit" : "miss"}">${esc(t)} <b class="tnum">×${n}</b></span>`).join("")}</div></td><td class="num tnum">${h.score.toFixed(2)}</td></tr>`).join("")}
        </tbody></table></div></section>`
        : `<section class="card empty"><div class="icon-wrap">${icon("search", 20)}</div><strong>No candidates match</strong>Boolean search is exact. Try expanding synonyms or using fewer AND terms.</section>`;
    } catch (e) { out.innerHTML = `<div class="notice bad">${icon("bad")}<span>${esc(e.message)}</span></div>`; }
  };
  $("#se-go").addEventListener("click", run);
  $("#se-q").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  $$("[data-ex]", main).forEach((b) => b.addEventListener("click", () => { $("#se-q").value = b.dataset.ex; run(); }));
  ["template", "layout", "format", "parser", "synonyms"].forEach((k) => $(`#se-${k}`).addEventListener("change", run));
  run();
}

// ------------------------------------------------------------------ charts
/* Grouped bar chart in SVG. spec = {categories, series:[{name, color, values:[{v, lo, hi}]}],
   max, fmt, unit, horizontal}. Colors are CSS variables so dark mode is automatic. */
const tip = () => $("#tooltip");
function showTip(html, x, y) {
  const t = tip();
  t.innerHTML = html;
  t.classList.add("show");
  const w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = `${Math.min(window.innerWidth - w - 8, Math.max(8, x - w / 2))}px`;
  t.style.top = `${Math.max(8, y - h - 12)}px`;
}
function hideTip() { const t = tip(); if (t) t.classList.remove("show"); }

function barChart(spec) {
  const id = `c${Math.random().toString(36).slice(2, 8)}`;
  const fmt = spec.fmt || ((v) => v.toFixed(2));
  const legend = `<div class="legend">${spec.series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</div>`;
  const W = 640, nC = spec.categories.length, nS = spec.series.length;
  let svg;
  if (spec.horizontal) {
    const rowH = Math.max(18, 8 + nS * 12), H = nC * (rowH + 16) + 30, L = 168, R = 40;
    const lo = Math.min(0, spec.min ?? 0), hi = spec.max ?? 1;
    const x = (v) => L + ((v - lo) / (hi - lo)) * (W - L - R);
    const ticks = spec.ticks || [lo, (lo + hi) / 2, hi];
    let g = ticks.map((t) => `<line class="gridline" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 24}"/><text class="tick-label" x="${x(t)}" y="${H - 8}" text-anchor="middle">${fmt(t)}</text>`).join("");
    g += `<line class="baseline" x1="${x(0)}" x2="${x(0)}" y1="0" y2="${H - 24}"/>`;
    spec.categories.forEach((cat, ci) => {
      const y0 = ci * (rowH + 16) + 8;
      g += `<text class="cat-label" x="${L - 10}" y="${y0 + rowH / 2 + 4}" text-anchor="end">${esc(cat)}</text>`;
      spec.series.forEach((s, si) => {
        const d = s.values[ci]; if (!d || d.v == null) return;
        const bh = (rowH - 2 * (nS - 1)) / nS, y = y0 + si * (bh + 2);
        const a = x(Math.min(0, d.v)), b = x(Math.max(0, d.v)), w = Math.max(2, b - a);
        g += `<rect class="bar-mark" data-s="${si}" x="${a}" y="${y}" width="${w}" height="${bh}" rx="3" fill="${s.color}"/>`;
        if (d.lo != null) g += `<line class="whisker" x1="${x(d.lo)}" x2="${x(d.hi)}" y1="${y + bh / 2}" y2="${y + bh / 2}"/>`;
        // label sits past the bar end and past its whisker, so the two never collide
        const lx = d.v < 0 ? Math.min(a, d.lo != null ? x(d.lo) : a) - 6 : Math.max(b, d.hi != null ? x(d.hi) : b) + 6;
        g += `<text class="tick-label" style="fill:var(--text-2);font-weight:600" x="${lx}" y="${y + bh / 2 + 4}" text-anchor="${d.v < 0 ? "end" : "start"}">${fmt(d.v)}</text>`;
        g += `<rect class="hit" data-c="${ci}" data-s="${si}" x="${L}" y="${y - 1}" width="${W - L - R}" height="${bh + 2}"/>`;
      });
    });
    svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(spec.label || "")}">${g}</svg>`;
  } else {
    const H = 280, L = 46, B = 38, T = 10, plotH = H - B - T;
    const hi = spec.max ?? 1;
    const y = (v) => T + plotH - (Math.max(0, v) / hi) * plotH;
    const groupW = (W - L) / nC, barW = Math.min(26, (groupW * 0.78 - 2 * (nS - 1)) / nS);
    const ticks = spec.ticks || [0, hi / 4, hi / 2, (3 * hi) / 4, hi];
    let g = ticks.map((t) => `<line class="${t === 0 ? "baseline" : "gridline"}" x1="${L}" x2="${W}" y1="${y(t)}" y2="${y(t)}"/><text class="tick-label" x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`).join("");
    spec.categories.forEach((cat, ci) => {
      const gx = L + ci * groupW + (groupW - (nS * barW + 2 * (nS - 1))) / 2;
      g += `<text class="cat-label" x="${L + ci * groupW + groupW / 2}" y="${H - 10}" text-anchor="middle">${esc(cat)}</text>`;
      spec.series.forEach((s, si) => {
        const d = s.values[ci]; if (!d || d.v == null) return;
        const bx = gx + si * (barW + 2), top = y(d.v), h = Math.max(1.5, y(0) - top);
        g += `<path class="bar-mark" data-s="${si}" fill="${s.color}" d="M${bx},${y(0)} V${top + Math.min(4, h)} Q${bx},${top} ${bx + Math.min(4, barW / 2)},${top} H${bx + barW - Math.min(4, barW / 2)} Q${bx + barW},${top} ${bx + barW},${top + Math.min(4, h)} V${y(0)} Z"/>`;
        if (d.lo != null && d.hi != null) g += `<line class="whisker" x1="${bx + barW / 2}" x2="${bx + barW / 2}" y1="${y(d.hi)}" y2="${y(d.lo)}"/><line class="whisker" x1="${bx + barW / 2 - 3}" x2="${bx + barW / 2 + 3}" y1="${y(d.hi)}" y2="${y(d.hi)}"/>`;
        g += `<rect class="hit" data-c="${ci}" data-s="${si}" x="${bx - 1}" y="${T}" width="${barW + 2}" height="${plotH}"/>`;
      });
    });
    svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(spec.label || "")}">${g}</svg>`;
  }
  const table = `<div class="table-wrap" hidden data-table><table class="data"><thead><tr><th></th>${spec.series.map((s) => `<th class="num">${esc(s.name)}</th>`).join("")}</tr></thead><tbody>
    ${spec.categories.map((c, ci) => `<tr><td>${esc(c)}</td>${spec.series.map((s) => { const d = s.values[ci]; return `<td class="num tnum">${d && d.v != null ? fmt(d.v) + (d.lo != null ? ` <span class="muted small">(${fmt(d.lo)} to ${fmt(d.hi)})</span>` : "") : "–"}</td>`; }).join("")}</tr>`).join("")}
    </tbody></table></div>`;
  setTimeout(() => wireChart(id, spec, fmt), 0);
  return `<div class="chart" id="${id}">${legend}<div data-plot>${svg}</div>${table}</div>`;
}

function wireChart(id, spec, fmt) {
  const el = document.getElementById(id);
  if (!el) return;
  $$(".hit", el).forEach((h) => {
    const ci = Number(h.dataset.c), si = Number(h.dataset.s);
    h.addEventListener("mousemove", (e) => {
      const s = spec.series[si], d = s.values[ci];
      el.classList.add("dim");
      $$(".bar-mark", el).forEach((b) => b.classList.toggle("on", Number(b.dataset.s) === si));
      showTip(`<b>${esc(spec.categories[ci])}</b><div class="t-row"><i style="background:${s.color}"></i>${esc(s.name)}: <b>${fmt(d.v)}</b></div>${d.lo != null ? `<div style="opacity:.75;margin-top:2px">95% CI ${fmt(d.lo)} to ${fmt(d.hi)}</div>` : ""}${spec.note ? `<div style="opacity:.75;margin-top:2px">${esc(spec.note)}</div>` : ""}`, e.clientX, e.clientY);
    });
    h.addEventListener("mouseleave", () => { el.classList.remove("dim"); hideTip(); });
  });
}

function chartCard(title, sub, chartHtml, figure) {
  return `<section class="card"><div class="card-head"><div><h2>${esc(title)}</h2><div class="sub">${esc(sub)}</div></div>
      <div class="seg" role="tablist" aria-label="View"><button type="button" aria-selected="true" data-view="chart">Chart</button><button type="button" aria-selected="false" data-view="table">Table</button></div></div>
    <div class="card-body">${chartHtml}
      <div class="chart-foot"><span>Whiskers show 95% confidence intervals where available.</span>${figure ? `<a href="${esc(figure)}" target="_blank" rel="noopener">Full figure ${icon("external", 12)}</a>` : ""}</div></div></section>`;
}

// ------------------------------------------------------------------ research
async function renderResearch(main) {
  main.innerHTML = `<div class="page"><div class="card card-body"><div class="skeleton" style="width:30%"></div><div class="skeleton" style="margin-top:14px"></div></div></div>`;
  let d;
  try { d = await api("/api/research"); } catch (e) { main.innerHTML = `<div class="page"><div class="notice bad">${icon("bad")}<span>${esc(e.message)}</span></div></div>`; return; }
  if (!d.available) { main.innerHTML = `<div class="page"><section class="card empty"><strong>No results yet</strong>Run <code>python scripts/run_experiments.py</code>.</section></div>`; return; }
  const S = d.series || {};
  const pct = (v) => `${Math.round(v * 100)}%`;
  const f2 = (v) => v.toFixed(2);
  const fig = (name) => (d.charts.find((c) => c.src.endsWith(name)) || {}).src;
  const cards = [];
  const LAY = ["single", "two_column", "table", "textbox"];
  if (S.layout) {
    const pick = (tpl, fmt) => LAY.map((l) => { const r = S.layout.find((x) => x.template === tpl && x.format === fmt && x.layout === l); return r ? { v: r.f1, lo: r.f1_lo, hi: r.f1_hi } : null; });
    cards.push(chartCard("Field extraction by layout", "Simple parser, F1 over 10 fields. Same content, only the layout changes.",
      barChart({ categories: LAY.map((l) => LAYOUT_LABELS[l]), max: 1, fmt: f2, label: "Field extraction F1 by layout",
        series: [{ name: "PDF, dev template", color: "var(--s1)", values: pick("classic", "pdf") }, { name: "PDF, held-out templates", color: "var(--s2)", values: pick("held_out_pooled", "pdf") },
          { name: "DOCX, dev template", color: "var(--s3)", values: pick("classic", "docx") }, { name: "DOCX, held-out templates", color: "var(--s4)", values: pick("held_out_pooled", "docx") }] }), fig("layout_f1.png")));
  }
  if (S.parsers) {
    const P = [["naive", "Ours, simple"], ["layout_aware", "Ours, layout-aware"], ["openresume", "OpenResume"], ["pyresparser", "pyresparser"], ["ensemble", "Combined vote"]].filter(([p]) => S.parsers.some((r) => r.parser === p));
    cards.push(chartCard("Parsers compared", "PDF, all five templates. F1 on the fields every engine attempts.",
      barChart({ categories: LAY.map((l) => LAYOUT_LABELS[l]), max: 1, fmt: f2, label: "Parser F1 by layout",
        series: P.map(([p, name], i) => ({ name, color: `var(--s${i + 1})`, values: LAY.map((l) => { const r = S.parsers.find((x) => x.parser === p && x.layout === l); return r ? { v: r.f1, lo: r.f1_lo, hi: r.f1_hi } : null; }) })) }), fig("parsers.png")));
  }
  if (S.synonyms) {
    const order2 = ["keyword", "tfidf", "skillner", "embedding", "keyword+taxonomy"].filter((s) => S.synonyms.some((r) => r.scorer === s));
    const names = { keyword: "Keyword", tfidf: "TF-IDF", skillner: "SkillNer", embedding: "Semantic", "keyword+taxonomy": "Keyword + aliases" };
    cards.push(chartCard("Synonym penalty", "Average score change when a resume says \"ML\" instead of \"machine learning\".",
      barChart({ horizontal: true, categories: order2.map((s) => names[s]), min: -0.35, max: 0.05, ticks: [-0.3, -0.2, -0.1, 0], fmt: (v) => `${v > 0 ? "+" : ""}${Math.round(v * 100)}%`, label: "Synonym penalty by scorer",
        series: [{ name: "Mean score change", color: "var(--s1)", values: order2.map((s) => { const r = S.synonyms.find((x) => x.scorer === s); return { v: r.mean_rel_delta, lo: r.rel_delta_lo, hi: r.rel_delta_hi }; }) }] }), fig("synonyms.png")));
  }
  if (S.stuffing) {
    const A = [["visible_repeat", "Visible keyword list"], ["hidden_keywords", "Hidden keywords"], ["hidden_jd", "Hidden pasted posting"]];
    const SC = [["keyword", "Keyword"], ["tfidf", "TF-IDF"], ["embedding", "Semantic"], ["skillner", "SkillNer"]].filter(([s]) => S.stuffing.some((r) => r.scorer === s));
    cards.push(chartCard("Keyword-stuffing audit", "Share of weak resumes that beat the best genuine one after stuffing.",
      barChart({ categories: A.map((a) => a[1]), max: 1, fmt: pct, label: "Stuffing success by scorer",
        series: SC.map(([s, name], i) => ({ name, color: `var(--s${i + 1})`, values: A.map(([a]) => { const r = S.stuffing.find((x) => x.attack === a && x.scorer === s); return r ? { v: r.beats_best_genuine, lo: r.beats_best_genuine_lo, hi: r.beats_best_genuine_hi } : null; }) })) }), fig("stuffing.png")));
  }
  const stab = S.stability_public || S.stability;
  if (stab) {
    const E = [["verb_swap", "Verb synonyms"], ["reorder_bullets", "Reordered bullets"], ["date_format", "Date format"], ["add_teamwork_bullet", "Generic bullet"], ["all_edits", "All edits"]];
    const SC = [["keyword", "Keyword"], ["tfidf", "TF-IDF"], ["embedding", "Semantic"]];
    const mx = Math.max(...stab.map((r) => r.mean_abs_rank_change), 1);
    const step = [1, 2, 2.5, 5, 10, 20, 25, 50].find((k) => mx / k <= 4) || 100;
    const top = Math.ceil(mx / step) * step;
    cards.push(chartCard("Ranking stability", `Average positions moved after one small edit (pool of ${S.stability_public ? 202 : 16}).`,
      barChart({ categories: E.map((e) => e[1]), max: top, ticks: Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step), fmt: (v) => (v % 1 ? v.toFixed(1) : String(v)), label: "Rank change by edit",
        series: SC.map(([s, name], i) => ({ name, color: `var(--s${i + 1})`, values: E.map(([e]) => { const r = stab.find((x) => x.edit === e && x.scorer === s); return r ? { v: r.mean_abs_rank_change } : null; }) })) }), fig("stability.png")));
  }
  const TPL = { modern: "Modern", latex: "LaTeX", career_center: "Career center", hybrid: "Hybrid" };
  if (S.learning && S.learning.templates) {
    const T = Object.keys(S.learning.templates);
    const L = (t, k) => { const x = S.learning.templates[t].line_acc[k]; return x ? { v: x.mean, lo: x.min, hi: x.max } : null; };
    const n = S.learning.teach || 8;
    cards.push(chartCard("Learning from corrections", "Lines labeled correctly on a template the network never saw, as corrected resumes arrive (5 runs).",
      barChart({ categories: T.map((t) => TPL[t] || t), max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], fmt: f2, label: "Line accuracy after teaching",
        series: [{ name: "No learning", color: "var(--muted)", values: T.map((t) => L(t, "start")) },
          { name: "1 corrected resume", color: "var(--s1)", values: T.map((t) => L(t, "after_1_corrected")) },
          { name: `${n} corrected`, color: "var(--s3)", values: T.map((t) => L(t, `after_${n}_corrected`)) },
          { name: `${n} of its own guesses`, color: "var(--s2)", values: T.map((t) => L(t, `after_${n}_self`)) }] }), fig("learning_curve.png")));
  }
  if (S.formats && S.formats.groups) {
    const G = S.formats.groups, K = Object.keys(G["hand-written"].line_acc);
    cards.push(chartCard("Training on generated formats", "Lines labeled correctly on templates and people never trained on, by how many of the 40 training formats were used.",
      barChart({ categories: K.map((k) => `${k} formats`), max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], fmt: f2, label: "Line accuracy by number of training formats",
        series: [{ name: "Hand-written templates (fair test)", color: "var(--s1)", values: K.map((k) => ({ v: G["hand-written"].line_acc[k] })) },
          { name: "Held-out generated formats", color: "var(--s2)", values: K.map((k) => ({ v: G.generated.line_acc[k] })) }] }), fig("format_diversity.png")));
  }
  if (S.geometry && S.geometry.groups) {
    const G = S.geometry.groups, GR = [["hand-written", "Hand-written"], ["generated", "Generated"], ["designer", "Designer"], ["reference", "Public templates"]].filter(([g]) => G[g]);
    const M = [["text", "Text only (app)"], ["geometry", "Geometry for every label"], ["headings", "Geometry for headings"]];
    cards.push(chartCard("Reading the page", "Lines labeled correctly on formats never trained on. Text only, the app's version, matched or beat the others here and on one real resume; see the README.",
      barChart({ categories: GR.map((g) => g[1]), max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], fmt: f2, label: "Line accuracy by use of page geometry",
        series: M.map(([m, name], i) => ({ name, color: ["var(--muted)", "var(--s2)", "var(--s1)"][i], values: GR.map(([g]) => ({ v: G[g][m].line_acc })) })) }), fig("geometry_ablation.png")));
  }
  if (S.visual && S.visual.readers) {
    const R = S.visual.readers, RD = [["rapidocr", "RapidOCR (app)"], ["florence", "Florence-2 (VLM)"], ["smolvlm", "SmolVLM-256M (VLM)"]].filter(([r]) => R[r]);
    const K = [["recall", "Words read"], ["found", "Image text found"], ["changed", "Words changed"]];
    cards.push(chartCard("Reading the page as an image", "OCR against two small vision-language models, on rendered resume pages whose text is known. Changed words are invented or altered; lower is better.",
      barChart({ categories: K.map((k) => k[1]), max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], fmt: f2, label: "Reading rendered resume pages",
        series: RD.map(([r, name], i) => ({ name, color: ["var(--s1)", "var(--s2)", "var(--s3)"][i], values: K.map(([k]) => ({ v: R[r][k] })) })) }), fig("visual_reading.png")));
  }
  main.innerHTML = `<div class="page">
    <div class="grid g4">${d.stats.map((s) => stat(esc(s.label), s.format === "pct" ? `${s.value.toFixed(0)}<small>%</small>` : s.value.toFixed(2), esc(s.detail))).join("")}</div>
    <div class="grid g2">${cards.join("")}</div>
    <p class="muted small">Numbers come from the committed experiment results. Methods and full tables are in the README and results/RESULTS.md.</p></div>`;
  $$(".card", main).forEach((card) => {
    const btns = $$("[data-view]", card);
    btns.forEach((b) => b.addEventListener("click", () => {
      btns.forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      const showTable = b.dataset.view === "table";
      $("[data-plot]", card).hidden = showTable; $(".legend", card).hidden = showTable; $("[data-table]", card).hidden = !showTable;
    }));
  });
}

// ------------------------------------------------------------------ about
function renderAbout(main) {
  const m = state.meta;
  main.innerHTML = `<div class="page"><div class="grid g-main">
      <section class="card"><div class="card-body prose">
        <div class="about-hero"><img src="logo.svg" width="64" height="64" alt="">
          <div><div class="about-name">ATS Simulator</div><div class="muted">A resume read the way a screening system reads it: line by line, looking for the terms that match.</div></div></div>
        <h3>What it models</h3>
        <p>Applicant tracking systems mostly do three things: turn a resume into fields, screen applicants out on knockout questions (work authorization, graduation date, GPA, degree), and let recruiters search and rank by keywords, sometimes with an AI match score. This app simulates those three stages.</p>
        <p>There is no single score that rejects people. Scores only order the candidates who pass the knockout rules, and a person decides what happens next.</p>
        <h3>What it does not claim</h3>
        <p>Commercial systems are proprietary. This is a simulator modeled on documented behavior, not a reproduction of Workday, Greenhouse, Lever, iCIMS or any other product.</p>
        <h3>Privacy</h3>
        <p>Everything runs on this computer. The app only listens for connections from this machine, and uploaded resumes are read, analyzed and deleted. It goes online only if you turn on update checks below, and then only to ask GitHub for the latest version number.</p>
        <h3>What it learns</h3>
        <p>The learned parser is a small neural network that labels each line with its section. It changes only when you click <em>Confirm and teach</em> on a resume, and it is saved on this computer. It learns where sections are, never which candidates are good: learning from hiring outcomes would copy whatever bias produced them.</p>
      </div></section>
      <section class="card"><div class="card-head"><h2>This installation</h2></div><div class="card-body">
        <dl class="kv">
          <dt>Version</dt><dd>${m ? esc(m.version) : "–"} <a class="small" href="https://github.com/shreyosecret/ATSResumeFilter/releases" target="_blank" rel="noopener">Releases</a><div class="small muted" id="update-line"></div></dd>
          <dt>Updates</dt><dd><label class="switch"><input type="checkbox" id="check-updates"><span><span class="small">Check for new versions</span></span></label>
            <div class="small muted" style="margin-top:4px">Off unless you turn it on. When on, the app asks GitHub for the latest version number; no resume data is sent.</div></dd>
          <dt>Semantic model</dt><dd>${m ? esc(m.embedding_backend || "unavailable") : "–"}</dd>
          <dt>Comparison pool</dt><dd>${m ? `${m.pool.size} resumes` : "–"}</dd>
          <dt>OpenResume</dt><dd>${m ? (m.engines.openresume ? '<span class="badge good"><span class="dot"></span>Installed</span>' : '<span class="badge neutral">Not installed</span>') : "–"}</dd>
          <dt>pyresparser</dt><dd>${m ? (m.engines.pyresparser ? '<span class="badge good"><span class="dot"></span>Installed</span>' : '<span class="badge neutral">Not installed</span>') : "–"}</dd>
          <dt>Learned parser</dt><dd id="about-model">–</dd>
          <dt>Visual check (OCR)</dt><dd>${m ? (m.engines.visual ? '<span class="badge good"><span class="dot"></span>Installed</span>' : '<span class="badge neutral">Not installed</span>') : "–"}</dd>
          <dt>SkillNer</dt><dd>${m ? (m.engines.skillner ? '<span class="badge good"><span class="dot"></span>Installed</span>' : '<span class="badge neutral">Not installed</span>') : "–"}</dd>
        </dl>
        <div class="divider"></div>
        <div class="small muted">Open-source components: OpenResume (AGPL-3.0) and pyresparser (GPL-3.0) run as separate programs; SkillNer (MIT); RapidOCR and PaddleOCR models (Apache-2.0); Inter typeface (SIL Open Font License).</div>
      </div></section>
    </div></div>`;
  api("/api/model").then((md) => {
    const el = $("#about-model");
    if (!el) return;
    el.innerHTML = !md.enabled ? '<span class="badge neutral">Off</span>'
      : md.ready ? `<span class="badge good"><span class="dot"></span>Ready</span> <span class="small muted">${md.taught} resume${md.taught === 1 ? "" : "s"} taught here</span>`
      : `<span class="badge neutral" title="${esc(md.status)}">Loading</span>`;
  }).catch(() => {});
  const box = $("#check-updates", main), line = $("#update-line", main);
  const show = (u) => {
    if (!u || !u.enabled) { line.textContent = ""; return; }
    line.innerHTML = u.error ? esc(u.error) : u.newer ? `Version ${esc(u.latest)} is available: <a href="${esc(u.url)}" target="_blank" rel="noopener">download it</a>.` : "You have the latest version.";
  };
  api("/api/settings").then((st) => { box.checked = st.check_updates; if (st.check_updates) api("/api/update").then(show).catch(() => {}); }).catch(() => {});
  box.addEventListener("change", async () => {
    try {
      await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ check_updates: box.checked }) });
      show(box.checked ? await api("/api/update") : null);
    } catch (err) { toast(err.message); }
  });
}

// ------------------------------------------------------------------ boot
$("#drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeDrawer(); hideTip(); } });
window.addEventListener("hashchange", route);
window.addEventListener("scroll", hideTip, { passive: true });
initTheme();
route();
pollStatus();
