"use strict";

const state = { token: "", workspace: null, activeJob: null, searchTimer: null, toastTimer: null, view: "forge" };
const $ = (id) => document.getElementById(id);
const all = (selector) => Array.from(document.querySelectorAll(selector));
const text = (id, value, fallback = "—") => { const node = $(id); if (node) node.textContent = value === null || value === undefined || value === "" ? fallback : String(value); };
const clamp = (value, min, max) => Math.min(max, Math.max(min, Number(value) || 0));
const title = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());

function bootstrapToken() {
  const url = new URL(location.href);
  const supplied = url.searchParams.get("token");
  if (supplied) {
    sessionStorage.setItem("dimwit-studio-token", supplied);
    url.searchParams.delete("token");
    history.replaceState({}, "", url.pathname + url.hash);
  }
  state.token = supplied || sessionStorage.getItem("dimwit-studio-token") || "";
}

async function api(path, options = {}) {
  const headers = { "X-Dimwit-Token": state.token, ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function toast(message, bad = false) {
  clearTimeout(state.toastTimer);
  text("toastIcon", bad ? "!" : "✓"); text("toastText", message);
  $("toastIcon").style.color = bad ? "var(--red)" : "var(--green)";
  $("toast").classList.remove("hidden");
  state.toastTimer = setTimeout(() => $("toast").classList.add("hidden"), 4400);
}

function setConnected(ok) {
  text("connectionLabel", ok ? "Studio connected" : "Studio disconnected");
  $("connectionDot").style.background = ok ? "var(--green)" : "var(--red)";
}

function setView(name) {
  state.view = name;
  all("[data-view]").forEach((node) => node.classList.toggle("active", node.dataset.view === name));
  all("[data-view-target]").forEach((node) => node.classList.toggle("active", node.dataset.viewTarget === name));
  location.hash = name === "forge" ? "" : name;
}

function meter(id, percent) { $(id).style.width = `${clamp(percent, 0, 100)}%`; }

function renderWorkspace(payload) {
  state.workspace = payload;
  const validation = payload.validation || {};
  const studio = payload.studio || {};
  const toolchains = payload.toolchains || {};
  const ecosystem = payload.ecosystem || {};
  text("reviewCeiling", payload.review_ceiling);
  text("validationVerdict", validation.verdict);
  const passed = Number((validation.counts || {}).PASS || 0), total = Number(validation.total || 0);
  text("validationCopy", `${passed}/${total} validators passing`); meter("validationMeter", total ? passed / total * 100 : 0);
  text("studioProgress", `${studio.complete || 0}/${studio.total || 0}`);
  text("studioCopy", `${studio.progress_percent || 0}% of the production graph proven`); meter("studioMeter", studio.progress_percent || 0);
  text("capabilityCount", payload.capabilities?.count || 0); meter("capabilityMeter", Math.min(100, (payload.capabilities?.count || 0) / 24 * 100));
  text("ecosystemCount", ecosystem.candidate_count || 0); text("ecosystemCopy", `${(ecosystem.evaluation_queue || []).length} candidates queued for evaluation`); meter("ecosystemMeter", ecosystem.state === "PASS" ? 100 : 30);
  text("systemStatus", validation.verdict === "PASS" ? "Proof green" : "Review state");
  $("systemStatus").className = `status-chip ${validation.verdict === "PASS" ? "good" : "bad"}`;
  text("proofValidation", validation.verdict); renderCounts(validation.counts || {});
  renderBoundaries(payload.boundaries || []); renderToolchains(toolchains); renderStudio(studio);
  renderBlockers(validation.non_pass || []); renderEvolution(payload.evolution || {}, payload.improvement_outcomes || {});
  renderEcosystem(ecosystem); renderEngines(payload.engines || {}, payload.cross_engine || {}); renderMobile(payload.mobile || {});
  renderProofRail(studio, payload.activity || {});
}

function renderBoundaries(rows) {
  const root = $("boundaryList"); root.replaceChildren();
  rows.slice(0, 6).forEach((value) => { const li = document.createElement("li"); li.textContent = value; root.append(li); });
}

function renderCounts(counts) {
  const root = $("validationCounts"); root.replaceChildren();
  ["PASS", "FAIL", "BLOCKED", "REJECTED"].forEach((name) => {
    const row = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = title(name); dd.textContent = String(counts[name] || 0); row.append(dt, dd); root.append(row);
  });
}

function renderToolchains(toolchains) {
  const blender = toolchains.blender || {}, unreal = toolchains.unreal || {};
  text("blenderVersion", blender.version || "Evidence missing");
  text("blenderDetail", blender.ok ? `${(blender.capabilities || []).length} production capabilities` : "Preflight required");
  text("unrealVersion", unreal.version ? `Unreal ${unreal.version}` : "Evidence missing");
  text("unrealDetail", unreal.ok ? `${(unreal.capabilities || []).length} production capabilities` : "Preflight required");
}

function renderStudio(studio) {
  const nodes = studio.nodes || [], root = $("studioGraph"); root.replaceChildren();
  text("graphTitle", `${studio.complete || 0} of ${studio.total || 0} nodes proven`);
  const next = (studio.next_nodes || [])[0]; text("nextNodeLabel", next ? `Next: ${title(next.id)}` : "No ready node");
  nodes.forEach((node, index) => {
    const card = document.createElement("article");
    const complete = ["PASS", "REVIEW_READY"].includes(node.status), ready = node.deps_ready && !complete;
    card.className = `node-card ${complete ? "pass" : ready ? "ready" : node.status === "BLOCKED" || node.status === "FAIL" ? "blocked" : ""}`;
    const marker = document.createElement("span"); marker.className = "node-index"; marker.textContent = complete ? "✓" : String(index + 1).padStart(2, "0");
    const copy = document.createElement("span"), strong = document.createElement("strong"), small = document.createElement("small");
    strong.textContent = title(node.id); small.textContent = `${title(node.kind)} · cost ${node.cost}`; copy.append(strong, small);
    const status = document.createElement("span"); status.className = "node-state"; status.textContent = ready ? "ready" : node.status;
    card.append(marker, copy, status); root.append(card);
  });
}

function renderBlockers(rows) {
  text("blockerCount", `${rows.length} current`); const root = $("blockerList"); root.replaceChildren();
  if (!rows.length) { root.innerHTML = '<div class="empty-state"><span>✓</span><div><strong>No non-pass validators</strong></div></div>'; return; }
  rows.forEach((row) => {
    const item = document.createElement("div"); item.className = "blocker-row";
    const status = document.createElement("span"); status.textContent = row.state;
    const name = document.createElement("strong"); name.textContent = `${title(row.domain)} · ${title(row.validator)}`;
    const reason = document.createElement("small"); reason.textContent = typeof row.reason === "string" ? row.reason : "Evidence requires review";
    item.append(status, name, reason); root.append(item);
  });
}

function renderEvolution(evolution, outcomes) {
  text("outcomeEligible", outcomes.eligible_proposals || 0); text("outcomeDecided", outcomes.decided || 0);
  text("outcomeAccepted", outcomes.accepted || 0);
  text("outcomeHitRate", outcomes.hit_rate === null || outcomes.hit_rate === undefined ? "Not measured" : `${(Number(outcomes.hit_rate) * 100).toFixed(1)}%`);
  const families = Object.values(evolution.families || {}).sort((a, b) => b.diversity_score - a.diversity_score || a.family.localeCompare(b.family));
  const grid = $("familyGrid"); grid.replaceChildren();
  families.slice(0, 4).forEach((row) => {
    const card = document.createElement("article"); card.className = "family-card";
    const name = document.createElement("span"), score = document.createElement("strong"), meta = document.createElement("small");
    name.textContent = row.family; score.textContent = Number(row.diversity_score || 0).toFixed(2); meta.textContent = `${row.attempts} attempts · budget ${row.candidate_budget}`;
    card.append(name, score, meta); grid.append(card);
  });
  const ranking = $("familyRanking"); ranking.replaceChildren(); const max = Math.max(...families.map((row) => row.diversity_score), 1);
  families.forEach((row) => {
    const item = document.createElement("div"); item.className = "family-row";
    const name = document.createElement("span"); name.textContent = title(row.family);
    const bar = document.createElement("span"); bar.className = "family-bar"; const fill = document.createElement("i"); fill.style.width = `${Math.max(2, row.diversity_score / max * 100)}%`; bar.append(fill);
    const score = document.createElement("span"); score.className = "family-score"; score.textContent = Number(row.diversity_score).toFixed(2);
    const meta = document.createElement("span"); meta.className = "family-meta"; meta.textContent = row.advisory_cooldown ? "cooling" : `${row.review_eligible}/${row.attempts}`;
    item.append(name, bar, score, meta); ranking.append(item);
  });
  const cooled = families.filter((row) => row.advisory_cooldown).map((row) => row.family); text("cooldownLabel", cooled.length ? `Advisory cooling: ${cooled.join(", ")}` : "No advisory cooldowns");
  const archive = $("championArchive"); archive.replaceChildren(); const champions = Object.entries(evolution.champion_archive || {});
  if (!champions.length) { const p = document.createElement("p"); p.className = "hero-copy"; p.textContent = "No review-eligible champions yet. This is honest empty evidence, not a fabricated score."; archive.append(p); }
  champions.forEach(([family, row]) => {
    const card = document.createElement("article"); card.className = "champion";
    const label = document.createElement("span"), score = document.createElement("strong"), task = document.createElement("small");
    label.textContent = title(family); score.textContent = Number(row.fitness_value || 0).toFixed(2); task.textContent = row.task_key || "Review candidate"; card.append(label, score, task); archive.append(card);
  });
}

function renderEcosystem(ecosystem) {
  text("ecosystemState", ecosystem.state); const root = $("ecosystemCards"); root.replaceChildren();
  (ecosystem.top || []).forEach((row) => {
    const card = document.createElement("article"); card.className = "ecosystem-card";
    const mode = document.createElement("span"), name = document.createElement("strong"), use = document.createElement("small"), score = document.createElement("b");
    mode.textContent = row.adoption_mode; name.textContent = row.name; use.textContent = row.use; score.textContent = `FIT ${Number(row.adoption_score).toFixed(1)} · ${row.license}`;
    card.append(mode, name, use, score); root.append(card);
  });
}

function renderEngines(engines, crossEngine) {
  text("engineAdapterCount", engines.adapter_count || 0); text("engineReadyCount", engines.ready_count || 0);
  text("engineTargetCount", (engines.targets || []).length); const root = $("engineCards"); root.replaceChildren();
  text("crossEngineState", crossEngine.state || "NOT_RUN");
  text("crossEngineDetail", crossEngine.comparable ? `${(crossEngine.engines || []).map(title).join(" + ")} · ${title(crossEngine.target)}` : ((crossEngine.issues || ["Proof not run"])[0]));
  (engines.engines || []).forEach((row) => {
    const card = document.createElement("article"); card.className = `engine-card ${row.ok ? "ready" : ""}`;
    const glyph = document.createElement("i"); glyph.textContent = row.engine.slice(0, 1);
    const copy = document.createElement("span"), name = document.createElement("strong"), detail = document.createElement("small");
    name.textContent = title(row.engine); detail.textContent = `${(row.targets || []).join(" · ")} · ${row.tool || (row.missing || []).join(", ")}`; copy.append(name, detail);
    const stateLabel = document.createElement("b"); stateLabel.textContent = row.ok ? "ready" : "blocked"; card.append(glyph, copy, stateLabel); root.append(card);
  });
  const targets = $("targetCloud"); targets.replaceChildren(); (engines.targets || []).forEach((target) => { const chip = document.createElement("span"); chip.textContent = target; targets.append(chip); });
}

function renderMobile(mobile) {
  const android = mobile.android || {}, ios = mobile.ios || {}, quality = mobile.quality || {};
  text("androidState", android.ok ? "Ready" : "Blocked");
  text("androidDetail", android.ok ? `SDK API ${android.maximum_platform_api} · build-tools ${android.build_tools}` : "Android SDK prerequisites missing");
  text("iosState", ios.ok ? "Ready" : "Mac required"); text("iosDetail", ios.ok ? "Xcode archive and simulator available" : ios.reason);
  text("mobileQualityTitle", `${quality.lane_count || 0} lanes · ${quality.check_count || 0} evidence checks`);
  const root = $("mobileQualityGrid"); root.replaceChildren();
  (quality.lanes || []).forEach((row, index) => {
    const card = document.createElement("article"); card.className = "quality-lane";
    const number = document.createElement("span"), name = document.createElement("strong"), checks = document.createElement("small");
    number.textContent = String(index + 1).padStart(2, "0"); name.textContent = title(row.id); checks.textContent = (row.checks || []).map(title).join(" · "); card.append(number, name, checks); root.append(card);
  });
}

function renderProofRail(studio, activity) {
  const next = studio.next_nodes || []; text("proofNext", next[0] ? title(next[0].id) : "None");
  const nextRoot = $("nextNodeList"); nextRoot.replaceChildren(); next.slice(0, 4).forEach((row) => { const p = document.createElement("p"); const name = document.createElement("span"), meta = document.createElement("span"); name.textContent = title(row.id); meta.textContent = `${row.kind} · ${row.cost}`; p.append(name, meta); nextRoot.append(p); });
  const review = activity.review_queue || []; text("reviewCount", review.length); const reviewRoot = $("reviewQueue"); reviewRoot.replaceChildren();
  if (!review.length) { const p = document.createElement("p"); p.textContent = "No candidate currently qualifies"; reviewRoot.append(p); }
  review.forEach((row) => { const p = document.createElement("p"); const name = document.createElement("span"), meta = document.createElement("span"); name.textContent = row.task_key || "Candidate"; meta.textContent = "review only"; p.append(name, meta); reviewRoot.append(p); });
}

async function loadWorkspace() {
  $("refreshButton").disabled = true;
  try { renderWorkspace(await api("/api/state")); setConnected(true); }
  catch (error) { setConnected(false); toast(error.message, true); }
  finally { $("refreshButton").disabled = false; }
}

async function startAction(action) {
  try {
    const job = await api("/api/actions", { method: "POST", body: JSON.stringify({ action }) });
    state.activeJob = job.id; renderJob(job); toast(`${job.label} started`); pollJobs();
  } catch (error) { toast(error.message, true); }
}

function renderJob(job) {
  if (!job) return;
  $("emptyJob").classList.add("hidden"); $("jobConsole").classList.remove("hidden");
  text("jobLabel", job.label); text("jobTime", job.started_at ? new Date(job.started_at * 1000).toLocaleTimeString() : "queued"); text("jobOutput", job.output || "Waiting for output…");
  text("jobStatus", title(job.status)); $("jobStatus").className = `status-chip ${job.status === "completed" ? "good" : job.status === "failed" ? "bad" : ""}`;
  $("jobOutput").scrollTop = $("jobOutput").scrollHeight;
}

async function pollJobs() {
  try {
    const payload = await api("/api/jobs"), jobs = payload.jobs || [];
    const current = jobs.find((job) => job.id === state.activeJob) || jobs[0]; if (current) renderJob(current);
    if (current && ["queued", "running"].includes(current.status)) setTimeout(pollJobs, 900); else if (current) { state.activeJob = null; loadWorkspace(); }
  } catch (error) { toast(error.message, true); }
}

function frameMission() {
  const mission = $("missionInput").value.trim();
  if (!mission) { toast("Describe a concrete game outcome first", true); return; }
  sessionStorage.setItem("dimwit-studio-mission", mission); toast("Mission framed locally. Choose an allowlisted proof action when ready.");
}

async function searchSource(query) {
  const root = $("sourceResults");
  if (query.trim().length < 2) { root.innerHTML = "<p>Type two characters to search approved first-party roots.</p>"; return; }
  try {
    const payload = await api(`/api/source?q=${encodeURIComponent(query)}`); root.replaceChildren();
    if (!payload.results.length) { const p = document.createElement("p"); p.textContent = "No approved source path matched."; root.append(p); return; }
    payload.results.forEach((result) => {
      const button = document.createElement("button"); button.className = "source-result";
      const name = document.createElement("strong"), path = document.createElement("small"); name.textContent = result.name; path.textContent = result.path; button.append(name, path);
      button.addEventListener("click", () => openSource(result.path, button)); root.append(button);
    });
  } catch (error) { toast(error.message, true); }
}

async function openSource(path, button) {
  try {
    const payload = await api(`/api/file?path=${encodeURIComponent(path)}`); text("sourcePath", payload.path); text("sourceBytes", `${payload.bytes.toLocaleString()} bytes`); text("sourceContent", payload.content);
    all(".source-result").forEach((node) => node.classList.remove("active")); button.classList.add("active");
  } catch (error) { toast(error.message, true); }
}

const commands = [
  { name: "Open Command Forge", description: "Production overview and bounded actions", key: "F", run: () => setView("forge") },
  { name: "Open Studio Graph", description: "Inspect the full Blender-to-release DAG", key: "S", run: () => setView("studio") },
  { name: "Open Universal Engines", description: "Inspect all engine adapters and platform targets", key: "U", run: () => setView("engines") },
  { name: "Open Mobile Factory", description: "Inspect Android, iOS, device, and store gates", key: "M", run: () => setView("mobile") },
  { name: "Open Improvement Lab", description: "Inspect diversity, champions, and open source", key: "E", run: () => setView("evolve") },
  { name: "Open Source Reader", description: "Search approved first-party source", key: "R", run: () => setView("source") },
  { name: "Plan Studio", description: "No-mutation 22-node production plan", key: "P", run: () => startAction("studio_plan") },
  { name: "Plan Recursive Improvement", description: "Evidence-ranked and review-bounded", key: "I", run: () => startAction("improvement_plan") },
  { name: "Run Slice Tests", description: "IDE and evolution safety regression tests", key: "T", run: () => startAction("slice_tests") },
  { name: "Audit Open Source", description: "No downloads or installs", key: "O", run: () => startAction("ecosystem_audit") },
  { name: "Audit Engines", description: "Inventory eight universal adapters", key: "G", run: () => startAction("engine_audit") },
  { name: "Audit Mobile", description: "Audit Android and iOS readiness", key: "A", run: () => startAction("mobile_audit") },
];

function renderPalette(filter = "") {
  const root = $("paletteList"); root.replaceChildren();
  commands.filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(filter.toLowerCase())).forEach((item, index) => {
    const button = document.createElement("button"); button.className = `palette-item${index === 0 ? " selected" : ""}`;
    const copy = document.createElement("span"), name = document.createElement("strong"), description = document.createElement("small"), key = document.createElement("span"); name.textContent = item.name; description.textContent = item.description; key.textContent = item.key; copy.append(name, description); button.append(copy, key);
    button.addEventListener("click", () => { closePalette(); item.run(); }); root.append(button);
  });
}
function openPalette() { $("palette").classList.remove("hidden"); $("paletteInput").value = ""; renderPalette(); setTimeout(() => $("paletteInput").focus(), 0); }
function closePalette() { $("palette").classList.add("hidden"); }

function bindEvents() {
  all("[data-view-target]").forEach((node) => node.addEventListener("click", () => setView(node.dataset.viewTarget)));
  all("[data-action]").forEach((node) => node.addEventListener("click", () => startAction(node.dataset.action)));
  $("refreshButton").addEventListener("click", loadWorkspace); $("commandButton").addEventListener("click", openPalette); $("paletteBackdrop").addEventListener("click", closePalette);
  $("paletteInput").addEventListener("input", (event) => renderPalette(event.target.value)); $("paletteInput").addEventListener("keydown", (event) => { if (event.key === "Enter") $("paletteList").querySelector(".palette-item")?.click(); });
  $("frameMissionButton").addEventListener("click", frameMission); $("sourceSearch").addEventListener("input", (event) => { clearTimeout(state.searchTimer); state.searchTimer = setTimeout(() => searchSource(event.target.value), 180); });
  document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openPalette(); } if (event.key === "Escape") closePalette(); });
  window.addEventListener("hashchange", () => { const value = location.hash.slice(1); if (["studio", "engines", "mobile", "evolve", "source"].includes(value)) setView(value); });
}

async function start() {
  bootstrapToken(); bindEvents(); $("missionInput").value = sessionStorage.getItem("dimwit-studio-mission") || "";
  const hash = location.hash.slice(1); if (["studio", "engines", "mobile", "evolve", "source"].includes(hash)) setView(hash);
  await loadWorkspace(); await pollJobs();
}
start();
