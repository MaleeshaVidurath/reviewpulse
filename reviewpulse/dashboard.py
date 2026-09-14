"""The ReviewPulse control-room dashboard: a single static HTML page,
served by the API itself (GET /) so it shares an origin with /api/* --
no CORS, no external sandbox, works by just opening the Function URL in
a browser.
"""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ReviewPulse Console</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
  :root {
    --ground: #f5f4f1;
    --surface: #ffffff;
    --surface-raised: #ffffff;
    --border: #e1ded6;
    --ink: #1c1a17;
    --ink-dim: #6b665c;
    --ink-faint: #9a9488;
    --accent: #d9622b;
    --accent-ink: #ffffff;
    --accent-soft: #fbe4d6;
    --good: #2f7a4f;
    --good-soft: #dcefe1;
    --warn: #b8801f;
    --warn-soft: #f6e7cd;
    --bad: #b3402f;
    --bad-soft: #f6ddd6;
    --shadow: 0 1px 2px rgba(28,26,23,0.06), 0 8px 24px -12px rgba(28,26,23,0.14);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #17161a;
      --surface: #1f1d22;
      --surface-raised: #26232a;
      --border: #38343c;
      --ink: #f0ede8;
      --ink-dim: #a8a29a;
      --ink-faint: #726c64;
      --accent: #e8763f;
      --accent-ink: #1a1310;
      --accent-soft: #3a2419;
      --good: #5fb583;
      --good-soft: #1c2e22;
      --warn: #d9a53f;
      --warn-soft: #332a17;
      --bad: #e07a63;
      --bad-soft: #362019;
      --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -12px rgba(0,0,0,0.5);
    }
  }
  :root[data-theme="dark"] {
    --ground: #17161a;
    --surface: #1f1d22;
    --surface-raised: #26232a;
    --border: #38343c;
    --ink: #f0ede8;
    --ink-dim: #a8a29a;
    --ink-faint: #726c64;
    --accent: #e8763f;
    --accent-ink: #1a1310;
    --accent-soft: #3a2419;
    --good: #5fb583;
    --good-soft: #1c2e22;
    --warn: #d9a53f;
    --warn-soft: #332a17;
    --bad: #e07a63;
    --bad-soft: #362019;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -12px rgba(0,0,0,0.5);
  }

  * { box-sizing: border-box; }
  html { color-scheme: light dark; }
  body {
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, sans-serif;
    padding-inline: 20px;
    padding-block: 28px 64px;
  }
  .mono { font-family: "IBM Plex Mono", ui-monospace, monospace; }
  .wrap { max-width: 1040px; margin: 0 auto; }

  header.top {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 22px;
  }
  .brand { display: flex; align-items: baseline; gap: 10px; }
  .brand .pulse-dot {
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    background: var(--accent); position: relative; top: -2px;
    box-shadow: 0 0 0 0 var(--accent);
    animation: pulse 2.4s ease-out infinite;
  }
  @media (prefers-reduced-motion: reduce) { .pulse-dot { animation: none; } }
  @keyframes pulse {
    0%   { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 55%, transparent); }
    70%  { box-shadow: 0 0 0 9px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
  }
  h1 { font-size: 1.3rem; font-weight: 700; margin: 0; letter-spacing: -0.01em; }
  .subtitle { color: var(--ink-dim); font-size: 0.82rem; }

  .key-field { display: flex; align-items: center; gap: 8px; font-size: 0.78rem; color: var(--ink-dim); }
  .key-field input {
    font-family: "IBM Plex Mono", monospace; font-size: 0.78rem;
    background: var(--surface); border: 1px solid var(--border); color: var(--ink);
    border-radius: 6px; padding: 6px 9px; width: 190px;
  }
  .key-field input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

  .banner {
    display: none;
    border: 1px solid var(--bad);
    background: var(--bad-soft);
    color: var(--bad);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 20px;
    font-size: 0.86rem;
    line-height: 1.5;
  }
  .banner.show { display: block; }
  .banner strong { display: block; font-size: 0.95rem; margin-bottom: 4px; }

  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 22px;
  }
  .tile {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: var(--shadow);
  }
  .tile .label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-faint); margin-bottom: 6px; }
  .tile .value { font-family: "IBM Plex Mono", monospace; font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .tile .value.ok { color: var(--good); }
  .tile .value.warn { color: var(--bad); }

  .action-row { display: flex; align-items: center; gap: 12px; margin-bottom: 26px; flex-wrap: wrap; }
  button {
    font-family: inherit; font-size: 0.86rem; font-weight: 600;
    border: none; border-radius: 8px; padding: 10px 18px; cursor: pointer;
    background: var(--accent); color: var(--accent-ink);
    transition: filter 0.15s ease;
  }
  button:hover { filter: brightness(1.08); }
  button:active { filter: brightness(0.95); }
  button:disabled { opacity: 0.5; cursor: not-allowed; filter: none; }
  button.ghost {
    background: transparent; color: var(--ink); border: 1px solid var(--border);
  }
  button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  input[type="number"] {
    font-family: "IBM Plex Mono", monospace; font-size: 0.86rem;
    background: var(--surface); border: 1px solid var(--border); color: var(--ink);
    border-radius: 8px; padding: 9px 10px; width: 72px;
  }
  .action-note { font-size: 0.78rem; color: var(--ink-faint); }

  section h2 {
    font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.07em;
    color: var(--ink-faint); font-weight: 600; margin: 0 0 12px;
  }
  section { margin-bottom: 30px; }

  .clusters { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
  .cluster-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 15px 16px; box-shadow: var(--shadow);
    display: flex; flex-direction: column; gap: 10px;
  }
  .cluster-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
  .cluster-title { font-weight: 600; font-size: 0.94rem; }
  .cluster-title .cat { color: var(--ink-dim); font-weight: 400; }
  .count-chip {
    font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; font-weight: 600;
    background: var(--accent-soft); color: var(--accent); border-radius: 999px;
    padding: 2px 9px; white-space: nowrap;
  }
  .sev-bar { display: flex; height: 6px; border-radius: 999px; overflow: hidden; background: var(--border); }
  .sev-bar span { display: block; }
  .sev-low { background: var(--good); }
  .sev-medium { background: var(--warn); }
  .sev-high, .sev-critical { background: var(--bad); }
  .sev-legend { display: flex; gap: 10px; font-size: 0.72rem; color: var(--ink-faint); font-family: "IBM Plex Mono", monospace; }
  .sample { font-size: 0.8rem; color: var(--ink-dim); line-height: 1.45; }
  .sample::before { content: "\201C"; }
  .sample::after { content: "\201D"; }
  .cluster-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 2px; }
  .ticket-link {
    font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; color: var(--good);
    text-decoration: none; font-weight: 600;
  }
  .ticket-link:hover { text-decoration: underline; }
  .sync-btn { padding: 6px 13px; font-size: 0.78rem; }
  .empty { color: var(--ink-faint); font-size: 0.85rem; padding: 18px 0; }

  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); box-shadow: var(--shadow); }
  th, td { text-align: left; padding: 9px 14px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  th { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-faint); font-weight: 600; }
  td.rating { font-family: "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums; }
  .pill {
    display: inline-block; font-size: 0.72rem; font-weight: 600; border-radius: 999px;
    padding: 2px 9px; font-family: "IBM Plex Mono", monospace;
  }
  .pill.negative { background: var(--bad-soft); color: var(--bad); }
  .pill.positive { background: var(--good-soft); color: var(--good); }
  .pill.neutral { background: var(--warn-soft); color: var(--warn); }
  .summary-cell { color: var(--ink-dim); max-width: 420px; }

  .toast {
    position: fixed; bottom: 20px; right: 20px; max-width: 360px;
    background: var(--surface-raised); border: 1px solid var(--border); color: var(--ink);
    border-radius: 10px; padding: 12px 15px; box-shadow: var(--shadow);
    font-size: 0.82rem; line-height: 1.4; opacity: 0; transform: translateY(6px);
    transition: opacity 0.2s ease, transform 0.2s ease; pointer-events: none;
  }
  .toast.show { opacity: 1; transform: translateY(0); }
  .toast.err { border-color: var(--bad); color: var(--bad); }

  footer { margin-top: 36px; font-size: 0.74rem; color: var(--ink-faint); text-align: center; }
  footer a { color: inherit; }
</style>
</head>
<body>
<div class="wrap">

  <header class="top">
    <div>
      <div class="brand">
        <span class="pulse-dot" aria-hidden="true"></span>
        <h1>ReviewPulse</h1>
      </div>
      <div class="subtitle">Triage console &middot; live pipeline, real Bedrock &amp; Jira</div>
    </div>
    <div class="key-field">
      <label for="apiKey">API key</label>
      <input id="apiKey" type="password" placeholder="required to run a tick / sync" autocomplete="off">
    </div>
  </header>

  <div id="crisisBanner" class="banner">
    <strong id="crisisHeadline">Crisis signal detected</strong>
    <span id="crisisBody"></span>
  </div>

  <div class="tiles">
    <div class="tile"><div class="label">Reviews triaged</div><div class="value mono" id="tileTriaged">&mdash;</div></div>
    <div class="tile"><div class="label">CSV cursor</div><div class="value mono" id="tileOffset">&mdash;</div></div>
    <div class="tile"><div class="label">Clusters</div><div class="value mono" id="tileClusters">&mdash;</div></div>
    <div class="tile"><div class="label">Crisis signal</div><div class="value mono" id="tileCrisis">&mdash;</div></div>
  </div>

  <div class="action-row">
    <button id="tickBtn">Run next tick</button>
    <label class="action-note" for="chunkSize">chunk size</label>
    <input id="chunkSize" type="number" min="1" max="100" value="20">
    <span class="action-note" id="tickStatus"></span>
  </div>

  <section>
    <h2>Clusters</h2>
    <div id="clusters" class="clusters"></div>
  </section>

  <section>
    <h2>Recent triaged reviews</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Rating</th><th>Sentiment</th><th>Category</th><th>Severity</th><th>Feature</th><th>Summary</th></tr></thead>
        <tbody id="reviewsBody"></tbody>
      </table>
    </div>
  </section>

  <footer>Deployed on AWS Lambda &middot; Bedrock Claude Haiku &amp; Sonnet &middot; DynamoDB &middot; Jira REST v3</footer>
</div>

<div class="toast" id="toast"></div>

<script>
const API = "";
const $ = (id) => document.getElementById(id);

function getKey() { return $("apiKey").value.trim(); }
$("apiKey").value = localStorage.getItem("reviewpulse_api_key") || "";
$("apiKey").addEventListener("input", () => localStorage.setItem("reviewpulse_api_key", getKey()));

let toastTimer;
function toast(msg, isErr) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 4200);
}

function severityBar(counts) {
  const order = ["low", "medium", "high", "critical"];
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const segs = order.filter(k => counts[k]).map(k =>
    `<span class="sev-${k}" style="width:${(counts[k] / total * 100).toFixed(1)}%"></span>`
  ).join("");
  const legend = order.filter(k => counts[k]).map(k => `${k} ${counts[k]}`).join(" &middot; ");
  return `<div class="sev-bar">${segs}</div><div class="sev-legend">${legend}</div>`;
}

function renderClusters(clusters, jiraBaseUrl) {
  const el = $("clusters");
  if (!clusters.length) {
    el.innerHTML = `<div class="empty">No clusters yet &mdash; run a tick to pull in reviews.</div>`;
    return;
  }
  el.innerHTML = clusters.map(c => {
    const ticket = c.ticket;
    const isPraise = c.category === "praise";
    const ticketHtml = ticket
      ? `<a class="ticket-link" href="${jiraBaseUrl}/browse/${ticket[0]}" target="_blank" rel="noopener">${ticket[0]} &middot; ${ticket[1]} reviews synced</a>`
      : `<span class="action-note">${isPraise ? "no ticket needed" : "not synced yet"}</span>`;
    const syncDisabled = isPraise ? "disabled title=\"pure praise, nothing to file\"" : "";
    return `
      <div class="cluster-card">
        <div class="cluster-head">
          <div class="cluster-title">${c.feature_area} <span class="cat">/ ${c.category}</span></div>
          <span class="count-chip">${c.count}</span>
        </div>
        ${severityBar(c.severity_counts)}
        <div class="sample">${c.sample_summaries[0] || ""}</div>
        <div class="cluster-foot">
          ${ticketHtml}
          <button class="sync-btn ghost" data-fa="${c.feature_area}" data-cat="${c.category}" ${syncDisabled}>Sync to Jira</button>
        </div>
      </div>`;
  }).join("");

  el.querySelectorAll(".sync-btn").forEach(btn => {
    btn.addEventListener("click", () => syncCluster(btn.dataset.fa, btn.dataset.cat, btn));
  });
}

function renderReviews(reviews) {
  $("reviewsBody").innerHTML = reviews.map(r => `
    <tr>
      <td class="rating">${r.rating}/5</td>
      <td><span class="pill ${r.sentiment}">${r.sentiment}</span></td>
      <td>${r.category}</td>
      <td>${r.severity}</td>
      <td>${r.feature_area}</td>
      <td class="summary-cell">${r.summary}</td>
    </tr>`).join("") || `<tr><td colspan="6" class="empty">Nothing triaged yet.</td></tr>`;
}

async function refreshStatus() {
  const res = await fetch(`${API}/api/status`);
  const data = await res.json();

  $("tileTriaged").textContent = data.total_triaged;
  $("tileOffset").textContent = data.offset;
  $("tileClusters").textContent = data.clusters.length;
  const crisisTile = $("tileCrisis");
  crisisTile.textContent = data.crisis.triggered ? "ACTIVE" : "quiet";
  crisisTile.className = "value mono " + (data.crisis.triggered ? "warn" : "ok");

  const banner = $("crisisBanner");
  if (data.crisis.triggered) {
    banner.classList.add("show");
    $("crisisBody").textContent =
      `Negative rate ${(data.crisis.recent_negative_rate * 100).toFixed(0)}% vs. baseline ${(data.crisis.baseline_negative_rate * 100).toFixed(0)}%.`;
  } else {
    banner.classList.remove("show");
  }

  renderClusters(data.clusters, data.jira_base_url || "");

  const revRes = await fetch(`${API}/api/reviews/recent?limit=15`);
  const revData = await revRes.json();
  renderReviews(revData.reviews);
}

async function runTick() {
  const key = getKey();
  if (!key) { toast("Enter your API key first.", true); return; }
  const btn = $("tickBtn");
  btn.disabled = true;
  $("tickStatus").textContent = "running triage against Bedrock…";
  try {
    const res = await fetch(`${API}/api/tick`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": key },
      body: JSON.stringify({ chunk_size: parseInt($("chunkSize").value, 10) || 20 }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail || "Tick failed", true); return; }
    if (data.status === "end_of_feed") { toast("Reached the end of the CSV feed."); return; }
    $("tickStatus").textContent = `+${data.new ?? 0} new, ${data.triaged ?? 0} triaged`;
    toast(`Tick complete: ${data.new ?? 0} new reviews, ${data.triaged ?? 0} triaged.`);
    await refreshStatus();
  } catch (e) {
    toast("Network error: " + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function syncCluster(featureArea, category, btn) {
  const key = getKey();
  if (!key) { toast("Enter your API key first.", true); return; }
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = "Syncing…";
  try {
    const res = await fetch(`${API}/api/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": key },
      body: JSON.stringify({ feature_area: featureArea, category }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail || "Sync failed", true); btn.textContent = original; btn.disabled = false; return; }
    toast(`${data.action === "created" ? "Created" : data.action === "commented" ? "Commented on" : "Already up to date:"} ${data.issue_key || ""}`.trim());
    await refreshStatus();
  } catch (e) {
    toast("Network error: " + e.message, true);
    btn.textContent = original;
    btn.disabled = false;
  }
}

$("tickBtn").addEventListener("click", runTick);
refreshStatus();
</script>
</body>
</html>
"""
