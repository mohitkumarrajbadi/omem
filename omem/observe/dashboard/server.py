"""OMem local GUI — CLI, MCP, audit, recall, and settings.

Zero-dependency loopback SPA. Run: ``omem dashboard`` or
``python -m omem.observe.dashboard.server``.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import socketserver
import threading
import webbrowser
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from ...api import OMem

logger = logging.getLogger(__name__)


_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OMem — Local GUI</title>
<style>
:root {
  --bg: #f7f6f3;
  --surface: #ffffff;
  --ink: #1a1a1a;
  --muted: #5c5c5c;
  --line: #d9d6cf;
  --accent: #0b3d2e;
  --accent-soft: #e6f0eb;
  --warn: #8a5a00;
  --warn-bg: #fff6e5;
  --bad: #8b1e1e;
  --bad-bg: #fceaea;
  --ok: #0b3d2e;
  --ok-bg: #e6f0eb;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --sans: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--sans); background: var(--bg); color: var(--ink); font-size: 13px; line-height: 1.45; min-height: 100vh; }
a { color: var(--accent); }
header.top { position: sticky; top: 0; z-index: 20; background: var(--surface); border-bottom: 1px solid var(--line); padding: 0.75rem 1.25rem 0.65rem; }
.brand-row { display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.55rem; }
.brand { font-size: 1.15rem; font-weight: 650; letter-spacing: -0.02em; }
.tagline { color: var(--muted); font-size: 0.85rem; }
.badge { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; border: 1px solid var(--line); padding: 0.1rem 0.4rem; color: var(--muted); }
.status-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.35rem 1rem; font-family: var(--mono); font-size: 11px; }
.status-strip .k { color: var(--muted); display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
.status-strip .v { color: var(--ink); word-break: break-all; }
.tabs { display: flex; gap: 0; border-bottom: 1px solid var(--line); background: var(--surface); padding: 0 1rem; overflow-x: auto; }
.tab-btn { background: none; border: none; border-bottom: 2px solid transparent; padding: 0.55rem 0.75rem; margin-bottom: -1px; cursor: pointer; color: var(--muted); font: inherit; font-weight: 500; white-space: nowrap; }
.tab-btn:hover { color: var(--ink); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
main { padding: 1rem 1.25rem 2rem; max-width: 1280px; margin: 0 auto; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.row { display: grid; gap: 0.75rem; }
.row.two { grid-template-columns: 1.15fr 1fr; }
.row.three { grid-template-columns: 1fr 1fr 1fr; }
@media (max-width: 900px) { .row.two, .row.three { grid-template-columns: 1fr; } }
.panel { background: var(--surface); border: 1px solid var(--line); padding: 0.75rem 0.85rem; }
.panel h2 { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; margin-bottom: 0.55rem; }
.toolbar { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin-bottom: 0.65rem; }
button, .btn { font: inherit; cursor: pointer; background: var(--accent); color: #fff; border: 1px solid var(--accent); padding: 0.35rem 0.7rem; }
button.secondary, .btn.secondary { background: var(--surface); color: var(--ink); border-color: var(--line); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
button.danger { background: var(--bad); border-color: var(--bad); }
input[type=text], input[type=search], input[type=number], textarea, select {
  font: inherit; font-family: var(--mono); font-size: 12px; border: 1px solid var(--line); background: var(--bg);
  padding: 0.35rem 0.5rem; min-width: 8rem; color: var(--ink);
}
textarea { width: 100%; min-height: 4.5rem; resize: vertical; font-family: var(--sans); }
label.field { display: block; margin-bottom: 0.55rem; }
label.field > span { display: block; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.2rem; }
label.check { display: flex; align-items: center; gap: 0.45rem; margin: 0.4rem 0; cursor: pointer; }
label.check input { min-width: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: left; color: var(--muted); font-weight: 550; border-bottom: 1px solid var(--line); padding: 0.3rem 0.35rem; font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; }
td { border-bottom: 1px solid var(--line); padding: 0.35rem; vertical-align: top; font-family: var(--mono); font-size: 11px; }
tr:hover td { background: var(--accent-soft); cursor: pointer; }
.pill { display: inline-block; padding: 0.05rem 0.35rem; border: 1px solid var(--line); font-size: 10px; font-family: var(--mono); }
.pill.ok { background: var(--ok-bg); border-color: #b7d4c6; color: var(--ok); }
.pill.bad { background: var(--bad-bg); border-color: #e3b6b6; color: var(--bad); }
.pill.warn { background: var(--warn-bg); border-color: #e6d3a6; color: var(--warn); }
.timeline { list-style: none; }
.timeline li { border-left: 2px solid var(--line); padding: 0.35rem 0 0.55rem 0.75rem; margin-left: 0.35rem; position: relative; }
.timeline li::before { content: ""; position: absolute; left: -5px; top: 0.55rem; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.timeline .step { font-weight: 600; font-size: 12px; }
.timeline .detail { color: var(--muted); font-family: var(--mono); font-size: 11px; white-space: pre-wrap; }
.muted { color: var(--muted); }
.mono { font-family: var(--mono); font-size: 11px; }
.scroll { max-height: 280px; overflow: auto; }
.scroll.tall { max-height: 420px; }
.scroll.xtall { max-height: 520px; }
#inspect-out, #prov-out, #demo-log, #mcp-json, #export-out, #tools-log, #health-out {
  font-family: var(--mono); font-size: 11px; white-space: pre-wrap;
  background: var(--bg); border: 1px solid var(--line); padding: 0.5rem; max-height: 280px; overflow: auto;
}
#graph-svg { width: 100%; height: 400px; background: var(--bg); border: 1px solid var(--line); }
.node circle { stroke: var(--line); stroke-width: 1; cursor: pointer; }
.node text { font-size: 10px; fill: var(--muted); pointer-events: none; }
.link { stroke: #c5c1b7; stroke-opacity: 0.7; }
.hint { color: var(--muted); font-size: 11px; }
.scorebar { display: inline-block; height: 6px; background: var(--accent); vertical-align: middle; max-width: 80px; }
.recall-row { border-bottom: 1px solid var(--line); padding: 0.45rem 0.2rem; }
.recall-row:hover { background: var(--accent-soft); cursor: pointer; }
.recall-row .top { display: flex; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }
.recall-row .content { font-family: var(--sans); font-size: 12.5px; margin: 0.2rem 0; }
.recall-row .meta { color: var(--muted); font-family: var(--mono); font-size: 10.5px; }
.score-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.35rem; margin-top: 0.4rem; }
.score-grid div { background: var(--bg); border: 1px solid var(--line); padding: 0.25rem; text-align: center; font-family: var(--mono); font-size: 10px; }
.score-grid .n { font-weight: 650; color: var(--accent); display: block; font-size: 12px; }
</style>
</head>
<body>
<header class="top">
  <div class="brand-row">
    <div class="brand">OMem</div>
    <div class="tagline">Local GUI — audit, recall, MCP, settings</div>
    <span class="badge">Local preview</span>
  </div>
  <div class="status-strip" id="status-strip">
    <div><span class="k">Session</span><span class="v" id="st-session">…</span></div>
    <div><span class="k">Namespace</span><span class="v" id="st-ns">…</span></div>
    <div><span class="k">DB</span><span class="v" id="st-db">…</span></div>
    <div><span class="k">Backend</span><span class="v" id="st-backend">…</span></div>
    <div><span class="k">Encryption</span><span class="v" id="st-enc">…</span></div>
    <div><span class="k">Memories</span><span class="v" id="st-mem">…</span></div>
    <div><span class="k">Last audit</span><span class="v" id="st-audit">…</span></div>
    <div><span class="k">Writes</span><span class="v" id="st-writes">…</span></div>
  </div>
</header>

<nav class="tabs" role="tablist">
  <button class="tab-btn active" data-tab="prove" type="button">Prove</button>
  <button class="tab-btn" data-tab="recall" type="button">Recall</button>
  <button class="tab-btn" data-tab="memory" type="button">Memory</button>
  <button class="tab-btn" data-tab="tools" type="button">Tools</button>
  <button class="tab-btn" data-tab="mcp" type="button">MCP</button>
  <button class="tab-btn" data-tab="play" type="button">Settings</button>
  <button class="tab-btn" data-tab="graph" type="button">Graph</button>
</nav>

<main>
  <section id="tab-prove" class="tab-panel active">
    <div class="toolbar">
      <button type="button" id="btn-demo">Run poison-recovery demo</button>
      <button type="button" class="secondary" id="btn-refresh-prove">Refresh</button>
      <span class="hint">Same story as <span class="mono">omem demo</span> — baseline → poison → provenance → rollback.</span>
    </div>
    <div class="row two">
      <div class="panel">
        <h2>Story timeline</h2>
        <ul class="timeline" id="timeline">
          <li><div class="step">Waiting</div><div class="detail">Run the demo to see baseline → poison → provenance → remediated.</div></li>
        </ul>
        <div id="demo-log" class="muted" style="margin-top:0.5rem;display:none"></div>
      </div>
      <div class="panel">
        <h2>Provenance</h2>
        <div class="toolbar">
          <input type="text" id="prov-id" placeholder="memory id" />
          <button type="button" class="secondary" id="btn-prov">Trace</button>
        </div>
        <div id="prov-out" class="muted">Select a memory or paste an id.</div>
      </div>
    </div>
    <div class="row two" style="margin-top:0.75rem">
      <div class="panel">
        <h2>Audit trail</h2>
        <div class="scroll tall"><table>
          <thead><tr><th>Time</th><th>Op</th><th>Actor</th><th>Entity</th><th>Detail</th></tr></thead>
          <tbody id="audit-body"><tr><td colspan="5" class="muted">Loading…</td></tr></tbody>
        </table></div>
      </div>
      <div class="panel">
        <h2>Snapshots</h2>
        <div class="toolbar">
          <input type="text" id="snap-label" placeholder="label (optional)" />
          <button type="button" class="secondary" id="btn-snap">Snapshot</button>
        </div>
        <p class="hint" style="margin-bottom:0.4rem">Enable writes in <strong>Settings</strong>.</p>
        <div class="scroll tall"><table>
          <thead><tr><th>Id</th><th>Label</th><th>Created</th><th></th></tr></thead>
          <tbody id="snap-body"><tr><td colspan="4" class="muted">Loading…</td></tr></tbody>
        </table></div>
      </div>
    </div>
  </section>

  <section id="tab-recall" class="tab-panel">
    <div class="panel">
      <h2>Recall <span class="muted">= omem recall / inspect</span></h2>
      <div class="toolbar">
        <input type="search" id="recall-q" placeholder="What should production use for payments?" style="flex:1;min-width:14rem" />
        <select id="recall-mode" title="mode">
          <option value="default">default</option>
          <option value="planning">planning</option>
          <option value="coding">coding</option>
          <option value="chat">chat</option>
          <option value="recall">recall</option>
          <option value="decisions">decisions</option>
          <option value="bugs">bugs</option>
          <option value="architecture">architecture</option>
        </select>
        <input type="number" id="recall-k" min="1" max="50" value="8" style="width:4.5rem;min-width:4.5rem" title="k" />
        <label class="check" style="margin:0"><input type="checkbox" id="recall-ns-only" checked /> <span class="hint">this NS</span></label>
        <button type="button" id="btn-recall">Recall</button>
        <button type="button" class="secondary" id="btn-recall-inspect">Explain</button>
      </div>
      <div class="row two">
        <div>
          <div id="recall-results" class="scroll xtall muted">Enter a query — ranked memories with scores and content.</div>
        </div>
        <div class="panel" style="padding:0.55rem">
          <h2>Score breakdown</h2>
          <div id="recall-detail" class="muted">Click a result to see vector / keyword / importance / recency / frequency.</div>
        </div>
      </div>
    </div>
  </section>

  <section id="tab-memory" class="tab-panel">
    <div class="panel">
      <div class="toolbar">
        <h2 style="margin:0;flex:1">All memories <span class="muted" id="mem-count"></span></h2>
        <input type="search" id="mem-filter" placeholder="filter content…" style="flex:1;max-width:16rem" />
        <button type="button" class="secondary" id="btn-refresh-mem">Refresh</button>
      </div>
      <div class="scroll xtall"><table>
        <thead><tr><th>Id</th><th>Type</th><th>Content</th><th>Imp</th><th>NS</th><th>Source</th></tr></thead>
        <tbody id="mem-body"></tbody>
      </table></div>
    </div>
  </section>

  <section id="tab-tools" class="tab-panel">
    <div class="row two">
      <div class="panel">
        <h2>CLI tools</h2>
        <p class="hint" style="margin-bottom:0.55rem">Local equivalents of common <span class="mono">omem</span> commands.</p>
        <div class="toolbar">
          <button type="button" class="secondary" id="btn-health">Health</button>
          <button type="button" class="secondary" id="btn-stats">Stats</button>
          <button type="button" class="secondary" id="btn-namespaces">Namespaces</button>
          <button type="button" class="secondary" id="btn-export">Export JSON</button>
        </div>
        <div class="toolbar">
          <select id="sleep-speed"><option value="normal">sleep normal</option><option value="fast">sleep fast</option><option value="deep">sleep deep</option></select>
          <button type="button" id="btn-sleep">Sleep / maintain</button>
          <button type="button" class="secondary" onclick="doCompress()">Compress</button>
          <button type="button" class="secondary" onclick="doReflect()">Reflect</button>
          <button type="button" class="secondary" onclick="doDecay()">Decay</button>
        </div>
        <div class="toolbar">
          <button type="button" class="danger" id="btn-clear-ns">Clear namespace</button>
          <span class="hint">Writes must be enabled in Settings.</span>
        </div>
        <div id="tools-log" class="muted" style="margin-top:0.5rem"></div>
      </div>
      <div class="panel">
        <h2>Output</h2>
        <div id="health-out" class="muted">Run Health / Stats / Namespaces / Export.</div>
        <div id="export-out" style="display:none;margin-top:0.5rem"></div>
      </div>
    </div>
  </section>

  <section id="tab-mcp" class="tab-panel">
    <div class="row two">
      <div class="panel">
        <h2>MCP settings</h2>
        <p class="hint" style="margin-bottom:0.55rem">Wire Claude Code / Cursor / OpenCode to this DB + namespace.</p>
        <label class="field"><span>MCP namespace</span>
          <input type="text" id="mcp-ns" style="width:100%" />
        </label>
        <label class="field"><span>DB path</span>
          <input type="text" id="mcp-db" style="width:100%" />
        </label>
        <label class="field"><span>Working mode</span>
          <select id="mcp-mode" style="width:100%">
            <option value="manual">manual — only when asked</option>
            <option value="auto" selected>auto — proactive remember + snapshot (recommended)</option>
            <option value="all">all — aggressive remember + frequent snapshots</option>
          </select>
        </label>
        <p class="hint" id="mcp-mode-hint" style="margin-bottom:0.45rem">auto: agent remembers decisions/prefs without you asking; snapshots before risk.</p>
        <div class="toolbar">
          <button type="button" class="secondary" id="btn-mcp-refresh">Preview config</button>
          <button type="button" class="secondary" id="btn-mcp-copy">Copy JSON</button>
          <button type="button" id="btn-mcp-cursor">Write ~/.cursor/mcp.json</button>
          <button type="button" class="secondary" id="btn-mcp-mode-save">Save mode locally</button>
        </div>
        <p class="hint">Install needs writes enabled. Restart Cursor/Claude after writing mcp.json.</p>
        <div id="mcp-log" class="mono muted" style="margin-top:0.4rem"></div>
      </div>
      <div class="panel">
        <h2>Client config</h2>
        <div id="mcp-json" class="muted">Loading…</div>
      </div>
    </div>
    <div class="panel" style="margin-top:0.75rem">
      <h2>OpenCode snippet</h2>
      <div id="mcp-opencode" class="mono muted scroll"></div>
    </div>
  </section>

  <section id="tab-play" class="tab-panel">
    <div class="row two">
      <div class="panel">
        <h2>Session settings</h2>
        <p class="hint" style="margin-bottom:0.6rem">What this GUI acts on. Loopback only.</p>
        <label class="field"><span>Session</span>
          <input type="text" id="set-session" placeholder="dashboard" style="width:100%" />
        </label>
        <label class="field"><span>Namespace</span>
          <input type="text" id="set-namespace" placeholder="default" style="width:100%" />
        </label>
        <label class="check">
          <input type="checkbox" id="set-play" />
          <span>Allow local writes (remember · snapshot · rollback · sleep · clear · MCP install)</span>
        </label>
        <div class="toolbar" style="margin-top:0.5rem">
          <button type="button" id="btn-apply-settings">Apply settings</button>
          <button type="button" class="secondary" id="btn-reload-settings">Reload</button>
        </div>
        <div id="settings-log" class="mono muted" style="margin-top:0.5rem"></div>
      </div>
      <div class="panel">
        <h2>Remember <span class="muted">= omem remember</span></h2>
        <label class="field"><span>Content</span>
          <textarea id="set-content" placeholder="Wire beneficiary is acct-100"></textarea>
        </label>
        <div class="toolbar">
          <label class="field" style="margin:0;flex:1"><span>Source</span>
            <input type="text" id="set-source" value="gui" style="width:100%;min-width:0" />
          </label>
          <label class="field" style="margin:0;width:7rem"><span>Importance</span>
            <input type="number" id="set-importance" min="0" max="1" step="0.05" placeholder="auto" style="width:100%;min-width:0" />
          </label>
        </div>
        <div class="toolbar">
          <button type="button" id="btn-remember">Remember</button>
          <button type="button" class="secondary" id="btn-play-snap">Snapshot now</button>
        </div>
        <div id="play-log" class="mono muted" style="margin-top:0.5rem"></div>
      </div>
    </div>
  </section>

  <section id="tab-graph" class="tab-panel">
    <div class="panel">
      <h2>Knowledge graph</h2>
      <p class="hint" id="graph-info" style="margin-bottom:0.5rem">Open this tab to load entities.</p>
      <svg id="graph-svg"></svg>
    </div>
  </section>
</main>

<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
<script>
let activeTab = 'prove';
let graphLoaded = false;
let pollTimer = null;
let cfg = { session_id: 'dashboard', namespace: 'default', play_writes: false, db_path: '' };
let lastRecall = [];

function withSession(url) {
  const sep = url.includes('?') ? '&' : '?';
  return url + sep + 'session=' + encodeURIComponent(cfg.session_id || 'dashboard')
    + '&namespace=' + encodeURIComponent(cfg.namespace || 'default');
}
async function fetchJSON(url) {
  const r = await fetch(withSession(url));
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function postJSON(url, body) {
  const payload = Object.assign({ session: cfg.session_id, namespace: cfg.namespace }, body || {});
  const r = await fetch(withSession(url), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function showTab(name) {
  activeTab = name;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name === 'graph' && !graphLoaded) loadGraph();
  if (name === 'play') loadSettingsForm();
  if (name === 'mcp') loadMcp();
  refreshActive();
}
document.querySelectorAll('.tab-btn').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));

async function loadStatus() {
  try {
    const s = await fetchJSON('/api/status');
    cfg.session_id = s.session_id || cfg.session_id;
    cfg.namespace = s.namespace || cfg.namespace;
    cfg.play_writes = !!s.play_writes;
    cfg.db_path = s.db_path || cfg.db_path;
    document.getElementById('st-session').textContent = s.session_id || '(none)';
    document.getElementById('st-ns').textContent = s.namespace || 'default';
    document.getElementById('st-db').textContent = s.db_path || '—';
    document.getElementById('st-backend').textContent = s.backend || '—';
    document.getElementById('st-enc').innerHTML = s.encryption ? '<span class="pill ok">on</span>' : '<span class="pill warn">off</span>';
    document.getElementById('st-mem').textContent = String(s.memory_count ?? '—');
    document.getElementById('st-audit').textContent = s.last_audit_at || '—';
    document.getElementById('st-writes').innerHTML = s.writes_allowed ? '<span class="pill ok">on</span>' : '<span class="pill warn">off</span>';
  } catch (e) { document.getElementById('st-session').textContent = 'error'; }
}

async function loadSettingsForm() {
  const s = await fetchJSON('/api/settings');
  cfg.session_id = s.session_id || cfg.session_id;
  cfg.namespace = s.namespace || cfg.namespace;
  cfg.play_writes = !!s.play_writes;
  document.getElementById('set-session').value = cfg.session_id;
  document.getElementById('set-namespace').value = cfg.namespace;
  document.getElementById('set-play').checked = cfg.play_writes;
}

function renderTimeline(report) {
  const ul = document.getElementById('timeline');
  if (!report) {
    ul.innerHTML = '<li><div class="step">Waiting</div><div class="detail">Run the demo.</div></li>';
    return;
  }
  const steps = [
    { step: 'Baseline', detail: 'legit=' + (report.legit_id || '') + '  snapshot=' + (report.snapshot_id || '') },
    { step: 'Poison injected', detail: 'poison=' + (report.poison_id || '') },
    { step: 'Provenance', detail: 'source=untrusted_web_scrape  actor=attacker' },
    { step: report.ok ? 'Remediated' : 'Failed', detail: (report.lines || []).slice(-2).join('\\n') },
  ];
  ul.innerHTML = steps.map(s => '<li><div class="step">' + s.step + '</div><div class="detail">' + escapeHtml(s.detail) + '</div></li>').join('');
  const log = document.getElementById('demo-log');
  log.style.display = 'block';
  log.textContent = (report.lines || []).join('\\n');
  if (report.poison_id) document.getElementById('prov-id').value = report.poison_id;
}

async function loadAudit() {
  const body = document.getElementById('audit-body');
  try {
    const rows = await fetchJSON('/api/audit?limit=40');
    if (!rows.length) { body.innerHTML = '<tr><td colspan="5" class="muted">No audit events yet.</td></tr>'; return; }
    body.innerHTML = rows.map(r => '<tr>' +
      '<td>' + escapeHtml(r.timestamp || r.ts || '') + '</td>' +
      '<td>' + escapeHtml(r.operation || r.op || r.action || '') + '</td>' +
      '<td>' + escapeHtml(r.actor || '') + '</td>' +
      '<td>' + escapeHtml(String(r.entity_id || r.memory_id || r.entity || '').slice(0, 14)) + '</td>' +
      '<td>' + escapeHtml(String(r.reason || r.detail || r.source || '').slice(0, 80)) + '</td></tr>').join('');
  } catch (e) { body.innerHTML = '<tr><td colspan="5" class="muted">' + escapeHtml(e.message) + '</td></tr>'; }
}

async function loadSnapshots() {
  const body = document.getElementById('snap-body');
  try {
    const rows = await fetchJSON('/api/snapshots');
    if (!rows.length) { body.innerHTML = '<tr><td colspan="4" class="muted">No snapshots for this session.</td></tr>'; return; }
    body.innerHTML = rows.map(r => '<tr>' +
      '<td>' + escapeHtml(String(r.id || '').slice(0, 18)) + '</td>' +
      '<td>' + escapeHtml(r.label || '') + '</td>' +
      '<td>' + escapeHtml(r.created_at || '') + '</td>' +
      '<td><button type="button" class="secondary" data-rollback="' + escapeHtml(r.id) + '">Rollback</button></td></tr>').join('');
    body.querySelectorAll('[data-rollback]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Rollback to ' + btn.dataset.rollback + '?')) return;
        try { await postJSON('/api/rollback', { snapshot_id: btn.dataset.rollback }); await refreshProve(); }
        catch (e) { alert(e.message); }
      });
    });
  } catch (e) { body.innerHTML = '<tr><td colspan="4" class="muted">' + escapeHtml(e.message) + '</td></tr>'; }
}

async function loadProvenance(id) {
  const out = document.getElementById('prov-out');
  if (!id) { out.textContent = 'Select a memory or paste an id.'; return; }
  out.textContent = 'Loading…';
  try { out.textContent = JSON.stringify(await fetchJSON('/api/provenance?id=' + encodeURIComponent(id)), null, 2); }
  catch (e) { out.textContent = e.message; }
}

async function runRecall(explain) {
  const q = document.getElementById('recall-q').value.trim();
  if (!q) return;
  const k = document.getElementById('recall-k').value || 8;
  const mode = document.getElementById('recall-mode').value;
  const nsOnly = document.getElementById('recall-ns-only').checked;
  const url = '/api/recall?q=' + encodeURIComponent(q) + '&k=' + encodeURIComponent(k)
    + '&mode=' + encodeURIComponent(mode) + '&project_only=' + (nsOnly ? '1' : '0')
    + '&explain=' + (explain ? '1' : '0');
  const box = document.getElementById('recall-results');
  box.innerHTML = 'Searching…';
  try {
    const data = await fetchJSON(url);
    lastRecall = data.results || [];
    if (!lastRecall.length) { box.innerHTML = '<span class="muted">No matches.</span>'; return; }
    const max = Math.max(...lastRecall.map(r => r.score || 0), 0.001);
    box.innerHTML = lastRecall.map((r, i) => {
      const w = Math.round(70 * ((r.score || 0) / max));
      return '<div class="recall-row" data-i="' + i + '">'
        + '<div class="top"><strong>#' + (i+1) + '</strong>'
        + ' <span class="pill">' + escapeHtml(r.type || '') + '</span>'
        + ' <span class="scorebar" style="width:' + w + 'px"></span>'
        + ' <span class="mono">' + Number(r.score || 0).toFixed(3) + '</span></div>'
        + '<div class="content">' + escapeHtml((r.content || '').slice(0, 280)) + '</div>'
        + '<div class="meta">' + escapeHtml((r.id || '').slice(0, 12))
        + ' · ns=' + escapeHtml(r.namespace || '')
        + ' · src=' + escapeHtml(r.source || '')
        + ' · imp=' + (r.importance != null ? Number(r.importance).toFixed(2) : '—')
        + '</div></div>';
    }).join('');
    box.querySelectorAll('.recall-row').forEach(el => {
      el.addEventListener('click', () => selectRecall(Number(el.dataset.i)));
    });
    selectRecall(0);
  } catch (e) { box.innerHTML = '<span class="muted">' + escapeHtml(e.message) + '</span>'; }
}

async function selectRecall(i) {
  const r = lastRecall[i];
  if (!r) return;
  const detail = document.getElementById('recall-detail');
  document.getElementById('prov-id').value = r.id || '';
  let scores = r.scores || null;
  if (!scores) {
    try {
      const ex = await fetchJSON('/api/inspect?q=' + encodeURIComponent(document.getElementById('recall-q').value.trim()));
      const hit = (ex || []).find(e => e.memory_id === r.id);
      if (hit) scores = {
        final: hit.final_score, vector: hit.vector_score, keyword: hit.keyword_score,
        importance: hit.importance_score, recency: hit.recency_score, frequency: hit.frequency_bonus,
        matched_keywords: hit.matched_keywords,
      };
    } catch (_) {}
  }
  let html = '<div class="content" style="font-family:var(--sans);margin-bottom:0.5rem">' + escapeHtml(r.content || '') + '</div>';
  if (scores) {
    html += '<div class="score-grid">'
      + '<div><span class="n">' + Number(scores.final ?? r.score ?? 0).toFixed(3) + '</span>final</div>'
      + '<div><span class="n">' + Number(scores.vector || 0).toFixed(2) + '</span>vector</div>'
      + '<div><span class="n">' + Number(scores.keyword || 0).toFixed(2) + '</span>keyword</div>'
      + '<div><span class="n">' + Number(scores.importance || 0).toFixed(2) + '</span>import.</div>'
      + '<div><span class="n">' + Number(scores.recency || 0).toFixed(2) + '</span>recency</div>'
      + '</div>';
    if (scores.matched_keywords && scores.matched_keywords.length)
      html += '<div class="hint" style="margin-top:0.4rem">keywords: ' + escapeHtml(scores.matched_keywords.join(', ')) + '</div>';
  } else {
    html += '<div class="hint">No score breakdown — click Explain.</div>';
  }
  html += '<div class="toolbar" style="margin-top:0.55rem">'
    + '<button type="button" class="secondary" id="btn-recall-prov">Provenance</button></div>';
  detail.innerHTML = html;
  document.getElementById('btn-recall-prov').onclick = () => { showTab('prove'); loadProvenance(r.id); };
}

let allMemories = [];
async function loadMemories() {
  allMemories = await fetchJSON('/api/memories');
  renderMemories();
}
function renderMemories() {
  const filter = (document.getElementById('mem-filter').value || '').toLowerCase();
  const mems = filter ? allMemories.filter(m => (m.content || '').toLowerCase().includes(filter)) : allMemories;
  document.getElementById('mem-count').textContent = '(' + mems.length + '/' + allMemories.length + ')';
  const tb = document.getElementById('mem-body');
  tb.innerHTML = mems.slice(0, 300).map(m => {
    const inactive = m.status === 'INACTIVE' || m.active === false;
    return '<tr data-mid="' + escapeHtml(m.id || '') + '" class="' + (inactive ? 'muted' : '') + '">'
      + '<td>' + escapeHtml((m.id || '').slice(0, 12)) + '</td>'
      + '<td><span class="pill">' + escapeHtml(m.type || '') + '</span></td>'
      + '<td style="font-family:var(--sans)">' + escapeHtml((m.content || '').slice(0, 120)) + '</td>'
      + '<td>' + (m.importance != null ? Number(m.importance).toFixed(2) : '') + '</td>'
      + '<td>' + escapeHtml(m.namespace || '') + '</td>'
      + '<td>' + escapeHtml(m.source || '') + '</td></tr>';
  }).join('') || '<tr><td colspan="6" class="muted">No memories.</td></tr>';
  tb.querySelectorAll('tr[data-mid]').forEach(tr => {
    tr.addEventListener('click', () => { showTab('prove'); document.getElementById('prov-id').value = tr.dataset.mid; loadProvenance(tr.dataset.mid); });
  });
}

async function doCompress() { try { const r = await postJSON('/api/compress'); toolOut(JSON.stringify(r)); await loadMemories(); } catch (e) { toolOut(e.message); } }
async function doReflect() { try { const r = await postJSON('/api/reflect'); toolOut('Reflected: ' + (r.length || 0)); await loadMemories(); } catch (e) { toolOut(e.message); } }
async function doDecay() { try { const r = await postJSON('/api/decay'); toolOut('Decayed: ' + (r.length || 0)); await loadMemories(); } catch (e) { toolOut(e.message); } }
function toolOut(msg) {
  const el = document.getElementById('tools-log');
  if (el) el.textContent = msg;
  const h = document.getElementById('health-out');
  if (h && activeTab === 'tools') h.textContent = typeof msg === 'string' ? msg : JSON.stringify(msg, null, 2);
}

async function loadGraph() {
  graphLoaded = true;
  const data = await fetchJSON('/api/graph');
  const svgEl = document.getElementById('graph-svg');
  const W = svgEl.clientWidth || 800, H = 400;
  const svg = d3.select(svgEl); svg.selectAll('*').remove();
  svg.attr('viewBox', [0, 0, W, H]);
  if (!data.nodes || !data.nodes.length) { document.getElementById('graph-info').textContent = 'No entities indexed yet.'; return; }
  document.getElementById('graph-info').textContent = data.nodes.length + ' entities · ' + (data.edges || []).length + ' edges';
  const colors = { CONCEPT: '#0b3d2e', PERSON: '#8a5a00', default: '#5c5c5c' };
  const sim = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-160))
    .force('center', d3.forceCenter(W / 2, H / 2));
  const link = svg.append('g').selectAll('line').data(data.edges).join('line').attr('class', 'link');
  const node = svg.append('g').selectAll('g').data(data.nodes).join('g').attr('class', 'node')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }))
    .on('click', async (e, d) => {
      document.getElementById('graph-info').textContent = d.id + ' — loading…';
      const related = await fetchJSON('/api/inspect?q=' + encodeURIComponent(d.id));
      document.getElementById('graph-info').textContent = d.id + ': ' +
        (related.slice(0, 3).map(r => r.memory_id.slice(0, 10) + '@' + r.final_score.toFixed(2)).join(' · ') || 'no hits');
    });
  node.append('circle').attr('r', d => Math.min(6 + (d.count || 1) * 1.5, 16)).attr('fill', d => colors[d.type] || colors.default);
  node.append('text').attr('dy', -10).attr('text-anchor', 'middle').text(d => d.id.length > 14 ? d.id.slice(0, 12) + '…' : d.id);
  sim.on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('transform', d => 'translate(' + d.x + ',' + d.y + ')');
  });
}

const MCP_MODE_HINTS = {
  manual: 'manual: remember/snapshot only when you explicitly ask.',
  auto: 'auto: agent remembers decisions/prefs without asking; snapshots before risk.',
  all: 'all: aggressive remember + frequent snapshots.',
};
function syncMcpModeHint() {
  const mode = document.getElementById('mcp-mode').value || 'auto';
  const el = document.getElementById('mcp-mode-hint');
  if (el) el.textContent = MCP_MODE_HINTS[mode] || MCP_MODE_HINTS.auto;
}
async function loadMcp() {
  try {
    const s = await fetchJSON('/api/mcp');
    document.getElementById('mcp-ns').value = s.namespace || cfg.namespace;
    document.getElementById('mcp-db').value = s.db_path || cfg.db_path || '';
    if (s.mode) document.getElementById('mcp-mode').value = s.mode;
    syncMcpModeHint();
    document.getElementById('mcp-json').textContent = JSON.stringify(s.cursor || s.config, null, 2);
    document.getElementById('mcp-opencode').textContent = JSON.stringify(s.opencode || {}, null, 2);
  } catch (e) { document.getElementById('mcp-json').textContent = e.message; }
}

async function refreshProve() { await Promise.all([loadStatus(), loadAudit(), loadSnapshots()]); }
async function refreshActive() {
  await loadStatus();
  if (activeTab === 'prove') await Promise.all([loadAudit(), loadSnapshots()]);
  if (activeTab === 'memory') await loadMemories();
  if (activeTab === 'play') await loadSettingsForm();
  if (activeTab === 'mcp') await loadMcp();
}

document.getElementById('btn-apply-settings').addEventListener('click', async () => {
  const log = document.getElementById('settings-log');
  try {
    const s = await postJSON('/api/settings', {
      session_id: document.getElementById('set-session').value.trim() || 'dashboard',
      namespace: document.getElementById('set-namespace').value.trim() || 'default',
      play_writes: document.getElementById('set-play').checked,
    });
    cfg.session_id = s.session_id; cfg.namespace = s.namespace; cfg.play_writes = !!s.play_writes;
    log.textContent = 'Applied. writes=' + (s.writes_allowed ? 'on' : 'off');
    await refreshActive();
  } catch (e) { log.textContent = e.message; }
});
document.getElementById('btn-reload-settings').addEventListener('click', loadSettingsForm);
document.getElementById('btn-remember').addEventListener('click', async () => {
  const log = document.getElementById('play-log');
  const content = document.getElementById('set-content').value.trim();
  if (!content) { log.textContent = 'Content required.'; return; }
  try {
    const impRaw = document.getElementById('set-importance').value;
    const body = { content, source: document.getElementById('set-source').value.trim() || 'gui' };
    if (impRaw !== '') body.importance = Number(impRaw);
    const r = await postJSON('/api/remember', body);
    log.textContent = 'Remembered ' + (r.memory_id || 'ok');
    document.getElementById('set-content').value = '';
    await loadStatus();
  } catch (e) { log.textContent = e.message; }
});
document.getElementById('btn-play-snap').addEventListener('click', async () => {
  const log = document.getElementById('play-log');
  try { const r = await postJSON('/api/snapshot', { label: 'gui-' + Date.now() }); log.textContent = 'Snapshot ' + (r.id || ''); await loadSnapshots(); }
  catch (e) { log.textContent = e.message; }
});
document.getElementById('btn-demo').addEventListener('click', async () => {
  const btn = document.getElementById('btn-demo');
  btn.disabled = true; btn.textContent = 'Running…';
  try {
    const report = await postJSON('/api/demo/poison-recovery');
    renderTimeline(report);
    if (report.poison_id) await loadProvenance(report.poison_id);
    await refreshProve();
  } catch (e) {
    document.getElementById('demo-log').style.display = 'block';
    document.getElementById('demo-log').textContent = e.message;
  } finally { btn.disabled = false; btn.textContent = 'Run poison-recovery demo'; }
});
document.getElementById('btn-refresh-prove').addEventListener('click', refreshProve);
document.getElementById('btn-refresh-mem').addEventListener('click', loadMemories);
document.getElementById('mem-filter').addEventListener('input', renderMemories);
document.getElementById('btn-prov').addEventListener('click', () => loadProvenance(document.getElementById('prov-id').value.trim()));
document.getElementById('btn-snap').addEventListener('click', async () => {
  try { await postJSON('/api/snapshot', { label: document.getElementById('snap-label').value || null }); await loadSnapshots(); }
  catch (e) { alert(e.message); }
});
document.getElementById('btn-recall').addEventListener('click', () => runRecall(false));
document.getElementById('btn-recall-inspect').addEventListener('click', () => runRecall(true));
document.getElementById('recall-q').addEventListener('keydown', e => { if (e.key === 'Enter') runRecall(false); });

document.getElementById('btn-health').addEventListener('click', async () => {
  try { document.getElementById('health-out').textContent = JSON.stringify(await fetchJSON('/api/health'), null, 2); }
  catch (e) { document.getElementById('health-out').textContent = e.message; }
});
document.getElementById('btn-stats').addEventListener('click', async () => {
  try { document.getElementById('health-out').textContent = JSON.stringify(await fetchJSON('/api/stats'), null, 2); }
  catch (e) { document.getElementById('health-out').textContent = e.message; }
});
document.getElementById('btn-namespaces').addEventListener('click', async () => {
  try { document.getElementById('health-out').textContent = JSON.stringify(await fetchJSON('/api/namespaces'), null, 2); }
  catch (e) { document.getElementById('health-out').textContent = e.message; }
});
document.getElementById('btn-export').addEventListener('click', async () => {
  try {
    const data = await fetchJSON('/api/export');
    document.getElementById('export-out').style.display = 'block';
    document.getElementById('export-out').textContent = JSON.stringify(data, null, 2).slice(0, 8000);
    document.getElementById('health-out').textContent = 'Exported ' + (data.count ?? (data.memories || []).length) + ' memories (truncated in panel).';
  } catch (e) { document.getElementById('health-out').textContent = e.message; }
});
document.getElementById('btn-sleep').addEventListener('click', async () => {
  try {
    const speed = document.getElementById('sleep-speed').value;
    const r = await postJSON('/api/sleep', { speed });
    document.getElementById('health-out').textContent = JSON.stringify(r, null, 2);
    await loadMemories();
  } catch (e) { document.getElementById('health-out').textContent = e.message; }
});
document.getElementById('btn-clear-ns').addEventListener('click', async () => {
  if (!confirm('Clear namespace "' + cfg.namespace + '"?')) return;
  try {
    const r = await postJSON('/api/clear', {});
    document.getElementById('health-out').textContent = JSON.stringify(r, null, 2);
    await loadMemories(); await loadStatus();
  } catch (e) { document.getElementById('health-out').textContent = e.message; }
});

document.getElementById('mcp-mode').addEventListener('change', syncMcpModeHint);
document.getElementById('btn-mcp-refresh').addEventListener('click', async () => {
  cfg.namespace = document.getElementById('mcp-ns').value.trim() || cfg.namespace;
  const db = document.getElementById('mcp-db').value.trim();
  const mode = document.getElementById('mcp-mode').value || 'auto';
  const s = await fetchJSON(
    '/api/mcp?db_path=' + encodeURIComponent(db)
    + '&mcp_namespace=' + encodeURIComponent(document.getElementById('mcp-ns').value.trim() || cfg.namespace)
    + '&mode=' + encodeURIComponent(mode)
  );
  document.getElementById('mcp-json').textContent = JSON.stringify(s.cursor || s.config, null, 2);
  document.getElementById('mcp-opencode').textContent = JSON.stringify(s.opencode || {}, null, 2);
  syncMcpModeHint();
});
document.getElementById('btn-mcp-copy').addEventListener('click', async () => {
  const text = document.getElementById('mcp-json').textContent;
  try { await navigator.clipboard.writeText(text); document.getElementById('mcp-log').textContent = 'Copied.'; }
  catch { document.getElementById('mcp-log').textContent = 'Copy failed — select manually.'; }
});
document.getElementById('btn-mcp-mode-save').addEventListener('click', async () => {
  const log = document.getElementById('mcp-log');
  try {
    const r = await postJSON('/api/mcp/mode', { mode: document.getElementById('mcp-mode').value || 'auto' });
    log.textContent = 'Mode saved: ' + (r.mode || '') + ' → ~/.omem/mcp_mode (restart MCP clients).';
  } catch (e) { log.textContent = e.message; }
});
document.getElementById('btn-mcp-cursor').addEventListener('click', async () => {
  const log = document.getElementById('mcp-log');
  try {
    const r = await postJSON('/api/mcp/install-cursor', {
      namespace: document.getElementById('mcp-ns').value.trim() || cfg.namespace,
      db_path: document.getElementById('mcp-db').value.trim() || cfg.db_path,
      mode: document.getElementById('mcp-mode').value || 'auto',
    });
    log.textContent = 'Wrote ' + (r.path || '~/.cursor/mcp.json') + ' mode=' + (r.mode || 'auto') + ' — restart Cursor.';
  } catch (e) { log.textContent = e.message; }
});

refreshActive();
pollTimer = setInterval(() => { if (!document.hidden) refreshActive(); }, 5000);
</script>
</body>
</html>
"""


def _session_id(
    params: Optional[Dict[str, List[str]]] = None,
    *,
    default: Optional[str] = None,
) -> str:
    if params and params.get("session"):
        return params["session"][0]
    return os.environ.get("OMEM_SESSION") or default or "dashboard"


def _agent_for(omem: OMem, session_id: str, namespace: Optional[str] = None):
    from ...agent_state import AgentState

    db_path = getattr(omem, "db_path", None) or os.environ.get("OMEM_DB")
    return AgentState(
        session_id=session_id,
        namespace=namespace or os.environ.get("OMEM_NS", "default"),
        db_path=db_path,
        backend=getattr(omem, "backend", None) or "sqlite",
    )


def _encryption_on(omem: OMem) -> bool:
    enc = getattr(omem, "_encryption", None) or getattr(omem, "encryption", None)
    if enc is not None:
        return True
    return bool(os.environ.get("OMEM_ENCRYPTION_KEY", "").strip())


def _normalize_audit(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x if isinstance(x, dict) else {"detail": str(x)} for x in payload]
    if isinstance(payload, dict):
        for key in ("events", "entries", "records", "audit", "items"):
            if isinstance(payload.get(key), list):
                return _normalize_audit(payload[key])
        return [payload]
    if isinstance(payload, str):
        try:
            return _normalize_audit(json.loads(payload))
        except json.JSONDecodeError:
            return [{"detail": payload}]
    return [{"detail": str(payload)}]


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the OMem dashboard."""

    omem: Optional[OMem] = None
    session_id: str = "dashboard"
    namespace: str = "default"
    play_writes: bool = False

    def log_message(self, format, *args):  # noqa: A003
        return

    def _send(self, data, content_type="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "null")
        self.end_headers()
        if isinstance(data, str):
            self.wfile.write(data.encode())
        else:
            self.wfile.write(json.dumps(data, default=str).encode())

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _writes_allowed(self) -> bool:
        # Play-tab toggle (loopback dashboard) wins for local experimentation.
        if getattr(self, "play_writes", False) or getattr(type(self), "play_writes", False):
            return True
        token = os.environ.get("OMEM_OBSERVE_TOKEN", "").strip()
        if token:
            return self.headers.get("Authorization", "") == f"Bearer {token}"
        return os.environ.get("OMEM_OBSERVE_ALLOW_MUTATE", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    def _mutate_allowed(self) -> bool:
        return self._writes_allowed()

    def _ns(self, params: Optional[Dict[str, List[str]]] = None, body: Optional[Dict[str, Any]] = None) -> str:
        if body and body.get("namespace"):
            return str(body["namespace"])
        if params and params.get("namespace"):
            return params["namespace"][0]
        return self.namespace or os.environ.get("OMEM_NS", "default")

    def _settings_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "namespace": self.namespace,
            "play_writes": bool(self.play_writes),
            "writes_allowed": self._writes_allowed(),
            "env_mutate": os.environ.get("OMEM_OBSERVE_ALLOW_MUTATE", "").strip().lower()
            in {"1", "true", "yes"},
            "db_path": getattr(self.omem, "db_path", None) if self.omem else None,
        }

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        omem = self.omem
        assert omem is not None

        if path in ("/", "/index.html"):
            self._send(_HTML, "text/html")
            return

        try:
            if path == "/api/status":
                self._send(self._api_status(params))
            elif path == "/api/stats":
                self._send(omem.stats())
            elif path == "/api/memories":
                mems = omem.all(include_inactive=True)
                self._send([m.to_dict() for m in mems])
            elif path == "/api/inspect":
                q = params.get("q", [""])[0]
                exps = omem.inspect(q, top_k=10)
                self._send(
                    [
                        {
                            "memory_id": e.memory_id,
                            "final_score": e.final_score,
                            "vector_score": e.vector_score,
                            "keyword_score": e.keyword_score,
                            "recency_score": e.recency_score,
                            "importance_score": e.importance_score,
                            "frequency_bonus": e.frequency_bonus,
                            "matched_keywords": e.matched_keywords,
                        }
                        for e in exps
                    ]
                )
            elif path == "/api/rag":
                q = params.get("q", [""])[0]
                results = omem.recall(q, top_k=10)
                self._send([m.to_dict() for m in results])
            elif path == "/api/graph":
                self._send(self._api_graph())
            elif path == "/api/audit":
                limit = int(params.get("limit", ["40"])[0] or 40)
                self._send(self._api_audit(params, limit=limit))
            elif path == "/api/provenance":
                mid = params.get("id", [""])[0]
                if not mid:
                    self._send({"error": "id required"}, code=400)
                    return
                self._send(self._api_provenance(params, mid))
            elif path == "/api/snapshots":
                self._send(self._api_snapshots(params))
            elif path == "/api/settings":
                self._send(self._settings_payload())
            elif path == "/api/health":
                self._send(self._api_health())
            elif path == "/api/namespaces":
                self._send(self._api_namespaces())
            elif path == "/api/export":
                self._send(self._api_export(params))
            elif path == "/api/recall":
                self._send(self._api_recall(params))
            elif path == "/api/mcp":
                self._send(self._api_mcp(params))
            else:
                self._send({"error": "not found"}, code=404)
        except Exception as exc:  # noqa: BLE001
            logger.exception("dashboard GET %s", path)
            self._send({"error": str(exc)}, code=500)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        body = self._read_json()
        params = parse_qs(urlparse(self.path).query)

        # Demo + settings are allowed without mutate gate (loopback play mode).
        if path == "/api/demo/poison-recovery":
            try:
                from ...demo.poison import run_poison_recovery

                report = run_poison_recovery()
                self._send(report)
            except Exception as exc:  # noqa: BLE001
                logger.exception("demo failed")
                self._send({"error": str(exc), "ok": False}, code=500)
            return

        if path == "/api/settings":
            if "session_id" in body or "session" in body:
                self.__class__.session_id = str(
                    body.get("session_id") or body.get("session") or self.session_id
                ).strip() or "dashboard"
            if "namespace" in body:
                self.__class__.namespace = str(body.get("namespace") or "default").strip() or "default"
            if "play_writes" in body:
                self.__class__.play_writes = bool(body.get("play_writes"))
            self._send(self._settings_payload())
            return

        # MCP working mode — local preference, no mutate gate
        if path == "/api/mcp/mode":
            try:
                from ...integrations.mcp_server import set_working_mode

                mode = str(body.get("mode") or "auto").strip().lower()
                self._send(set_working_mode(mode, persist=True))
            except Exception as exc:  # noqa: BLE001
                self._send({"error": str(exc)}, code=400)
            return

        if not self._mutate_allowed():
            token = os.environ.get("OMEM_OBSERVE_TOKEN", "").strip()
            if token and self.headers.get("Authorization", "") != f"Bearer {token}":
                self._send({"error": "unauthorized"}, code=401)
                return
            self._send(
                {
                    "error": (
                        "writes disabled — open Settings and enable "
                        "'Allow local writes', or set OMEM_OBSERVE_ALLOW_MUTATE=1"
                    )
                },
                code=403,
            )
            return

        omem = self.omem
        assert omem is not None
        ns = self._ns(params, body)

        try:
            if path == "/api/compress":
                self._send(omem.compress())
            elif path == "/api/reflect":
                refs = omem.reflect()
                self._send([m.to_dict() for m in refs])
            elif path == "/api/decay":
                self._send(omem.decay())
            elif path == "/api/remember":
                content = (body.get("content") or "").strip()
                if not content:
                    self._send({"error": "content required"}, code=400)
                    return
                importance = body.get("importance")
                if importance is not None:
                    try:
                        importance = float(importance)
                    except (TypeError, ValueError):
                        importance = None
                mid = omem.add(
                    content,
                    namespace=ns,
                    source=str(body.get("source") or "dashboard"),
                    importance=importance,
                    metadata={"actor": "dashboard", "session": self.session_id},
                )
                self._send({"ok": True, "memory_id": mid, "namespace": ns})
            elif path == "/api/snapshot":
                sess = body.get("session") or _session_id(params, default=self.session_id)
                agent = _agent_for(omem, sess, namespace=ns)
                snap = agent.snapshot(label=body.get("label"))
                self._send(
                    {
                        "id": snap.id,
                        "label": getattr(snap, "label", None),
                        "created_at": getattr(snap, "created_at", None),
                    }
                )
            elif path == "/api/rollback":
                sid = body.get("snapshot_id")
                if not sid:
                    self._send({"error": "snapshot_id required"}, code=400)
                    return
                sess = body.get("session") or _session_id(params, default=self.session_id)
                agent = _agent_for(omem, sess, namespace=ns)
                agent.rollback(sid)
                self._send({"ok": True, "snapshot_id": sid})
            elif path == "/api/sleep":
                speed = str(body.get("speed") or "normal")
                result = omem.sleep(speed=speed) if hasattr(omem, "sleep") else {"error": "sleep unsupported"}
                if hasattr(result, "to_dict"):
                    result = result.to_dict()
                self._send(result if isinstance(result, dict) else {"result": result})
            elif path == "/api/clear":
                omem.clear(namespace=ns)
                self._send({"ok": True, "cleared_namespace": ns})
            elif path == "/api/mcp/install-cursor":
                from ...demo.story import mcp_config, merge_cursor_mcp
                from ...integrations.mcp_server import set_working_mode

                db = str(
                    body.get("db_path")
                    or getattr(omem, "db_path", None)
                    or os.path.expanduser("~/.omem/brain.db")
                )
                mcp_ns = str(body.get("namespace") or ns or "personal")
                mode = str(body.get("mode") or "auto").strip().lower() or "auto"
                try:
                    set_working_mode(mode, persist=True)
                except ValueError:
                    mode = "auto"
                    set_working_mode(mode, persist=True)
                block = mcp_config(db, namespace=mcp_ns, mode=mode)
                path_written = merge_cursor_mcp(block)
                self._send({"ok": True, "path": path_written, "config": block, "mode": mode})
            else:
                self._send({"error": "not found"}, code=404)
        except Exception as exc:  # noqa: BLE001
            logger.exception("dashboard POST %s", path)
            self._send({"error": str(exc)}, code=500)

    def _api_status(self, params: Dict[str, List[str]]) -> Dict[str, Any]:
        omem = self.omem
        assert omem is not None
        session = _session_id(params, default=self.session_id)
        stats = omem.stats() if hasattr(omem, "stats") else {}
        mem_count = stats.get("total") or stats.get("active") or stats.get("count")
        if mem_count is None:
            try:
                mem_count = len(omem.all(include_inactive=True))
            except Exception:
                mem_count = None
        last_audit = None
        try:
            rows = self._api_audit(params, limit=1)
            if rows:
                last_audit = rows[0].get("timestamp") or rows[0].get("ts") or rows[0].get("created_at")
        except Exception:
            pass
        return {
            "session_id": session,
            "namespace": self._ns(params),
            "db_path": getattr(omem, "db_path", None) or os.environ.get("OMEM_DB") or os.path.expanduser("~/.omem/brain.db"),
            "backend": getattr(omem, "backend", None) or "sqlite",
            "encryption": _encryption_on(omem),
            "memory_count": mem_count,
            "last_audit_at": last_audit,
            "play_writes": bool(self.play_writes),
            "writes_allowed": self._writes_allowed(),
            "product": "Audit & rollback for AI agents",
        }

    def _api_audit(self, params: Dict[str, List[str]], limit: int = 40) -> List[Dict[str, Any]]:
        omem = self.omem
        assert omem is not None
        session = _session_id(params, default=self.session_id)
        agent = _agent_for(omem, session, namespace=self._ns(params))
        body = agent.governance.export_audit(format="json", limit=limit)
        rows = _normalize_audit(body)
        return rows[:limit]

    def _api_provenance(self, params: Dict[str, List[str]], memory_id: str) -> Dict[str, Any]:
        omem = self.omem
        assert omem is not None
        session = _session_id(params, default=self.session_id)
        agent = _agent_for(omem, session, namespace=self._ns(params))
        mem = None
        try:
            mem = omem.get(memory_id)
        except Exception:
            mem = None
        chain = None
        try:
            chain = agent.provenance.trace(memory_id)
        except Exception:
            try:
                chain = agent.provenance.history(entity_id=memory_id, limit=50)
            except Exception as exc:
                return {
                    "memory_id": memory_id,
                    "error": str(exc),
                    "memory": mem.to_dict() if mem is not None and hasattr(mem, "to_dict") else None,
                }
        events = getattr(chain, "events", None)
        if events is None and isinstance(chain, list):
            events = chain
        event_rows = []
        for ev in events or []:
            if hasattr(ev, "to_dict"):
                event_rows.append(ev.to_dict())
            elif isinstance(ev, dict):
                event_rows.append(ev)
            else:
                event_rows.append({"detail": str(ev)})
        meta = {}
        if mem is not None:
            meta = getattr(mem, "metadata", None) or {}
            if not isinstance(meta, dict):
                meta = {}
        return {
            "memory_id": memory_id,
            "source": getattr(mem, "source", None) if mem is not None else None,
            "namespace": getattr(mem, "namespace", None) if mem is not None else None,
            "actor": meta.get("actor"),
            "trust": meta.get("trust"),
            "content_preview": (getattr(mem, "content", None) or "")[:200] if mem is not None else None,
            "events": event_rows,
            "event_count": len(event_rows),
        }

    def _api_snapshots(self, params: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        omem = self.omem
        assert omem is not None
        session = _session_id(params, default=self.session_id)
        agent = _agent_for(omem, session, namespace=self._ns(params))
        snaps = agent.list_snapshots()
        out = []
        for s in snaps:
            if hasattr(s, "to_dict"):
                out.append(s.to_dict())
            else:
                out.append(
                    {
                        "id": getattr(s, "id", None),
                        "label": getattr(s, "label", None),
                        "created_at": getattr(s, "created_at", None),
                    }
                )
        return out


    def _api_health(self) -> Dict[str, Any]:
        omem = self.omem
        assert omem is not None
        stats = omem.stats() if hasattr(omem, "stats") else {}
        return {
            "ok": True,
            "backend": getattr(omem, "backend", None) or "sqlite",
            "db_path": getattr(omem, "db_path", None),
            "encryption": _encryption_on(omem),
            "session_id": self.session_id,
            "namespace": self.namespace,
            "stats": stats,
            "writes_allowed": self._writes_allowed(),
        }

    def _api_namespaces(self) -> Dict[str, Any]:
        omem = self.omem
        assert omem is not None
        names = omem.namespaces() if hasattr(omem, "namespaces") else []
        detail = []
        for n in names:
            try:
                detail.append({"namespace": n, **(omem.namespace_stats(n) if hasattr(omem, "namespace_stats") else {})})
            except Exception:
                detail.append({"namespace": n})
        return {"namespaces": names, "detail": detail}

    def _api_export(self, params: Dict[str, List[str]]) -> Dict[str, Any]:
        omem = self.omem
        assert omem is not None
        ns = self._ns(params)
        mems = omem.all(include_inactive=True)
        if ns and ns != "default":
            mems = [m for m in mems if getattr(m, "namespace", None) == ns]
        rows = [m.to_dict() for m in mems]
        return {"count": len(rows), "namespace": ns, "memories": rows}

    def _api_recall(self, params: Dict[str, List[str]]) -> Dict[str, Any]:
        omem = self.omem
        assert omem is not None
        q = params.get("q", [""])[0]
        if not q:
            return {"query": "", "results": []}
        k = int(params.get("k", ["8"])[0] or 8)
        mode = params.get("mode", ["default"])[0] or "default"
        project_only = params.get("project_only", ["1"])[0] in {"1", "true", "yes"}
        explain = params.get("explain", ["0"])[0] in {"1", "true", "yes"}
        ns = self._ns(params)
        mems = omem.recall(
            q,
            k=k,
            mode=mode if mode != "default" else None,
            namespace=ns,
            project_only=project_only,
            explain=True,
        )
        score_by_id: Dict[str, Any] = {}
        try:
            inspected = omem.inspect(q, top_k=max(k, 12), namespace=ns)
        except TypeError:
            inspected = omem.inspect(q, top_k=max(k, 12))
        for e in inspected:
            score_by_id[e.memory_id] = {
                "final": e.final_score,
                "vector": e.vector_score,
                "keyword": e.keyword_score,
                "importance": e.importance_score,
                "recency": e.recency_score,
                "frequency": e.frequency_bonus,
                "matched_keywords": getattr(e, "matched_keywords", None) or [],
            }
        results = []
        for rank, m in enumerate(mems, 1):
            mid = getattr(m, "id", None)
            sc = score_by_id.get(mid) if mid else None
            results.append(
                {
                    "id": mid,
                    "rank": rank,
                    "content": getattr(m, "content", None),
                    "type": getattr(getattr(m, "type", None), "name", None)
                    or str(getattr(m, "type", "") or ""),
                    "namespace": getattr(m, "namespace", None),
                    "source": getattr(m, "source", None),
                    "importance": getattr(m, "importance", None),
                    "score": (sc or {}).get("final"),
                    "scores": sc,
                }
            )
        # Prefer inspect ranking when scores missing on recall hits
        if results and all(r.get("score") is None for r in results) and score_by_id:
            ordered = []
            for e in inspected[:k]:
                mid = e.memory_id
                mem = next((m for m in mems if getattr(m, "id", None) == mid), None)
                if mem is None:
                    continue
                sc = score_by_id[mid]
                ordered.append(
                    {
                        "id": mid,
                        "rank": len(ordered) + 1,
                        "content": getattr(mem, "content", None),
                        "type": getattr(getattr(mem, "type", None), "name", None)
                        or str(getattr(mem, "type", "") or ""),
                        "namespace": getattr(mem, "namespace", None),
                        "source": getattr(mem, "source", None),
                        "importance": getattr(mem, "importance", None),
                        "score": sc.get("final"),
                        "scores": sc,
                    }
                )
            if ordered:
                results = ordered
        return {
            "query": q,
            "k": k,
            "mode": mode,
            "namespace": ns,
            "explain": explain,
            "results": results,
        }

    def _api_mcp(self, params: Dict[str, List[str]]) -> Dict[str, Any]:
        from ...demo.story import mcp_config, resolve_omem_bin
        from ...integrations.mcp_server import get_working_mode

        omem = self.omem
        assert omem is not None
        db = params.get("db_path", [None])[0] or getattr(omem, "db_path", None) or os.path.expanduser("~/.omem/brain.db")
        mcp_ns = params.get("mcp_namespace", [None])[0] or self.namespace or "personal"
        mode = (params.get("mode", [None])[0] or get_working_mode() or "auto").strip().lower()
        if mode not in {"manual", "auto", "all"}:
            mode = "auto"
        block = mcp_config(str(db), namespace=str(mcp_ns), mode=mode)
        server = block["mcpServers"]["omem"]
        opencode = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "omem": {
                    "type": "local",
                    "command": [server["command"], *server["args"]],
                    "enabled": True,
                }
            },
        }
        return {
            "namespace": mcp_ns,
            "db_path": db,
            "mode": mode,
            "omem_bin": resolve_omem_bin(),
            "config": block,
            "cursor": block,
            "opencode": opencode,
            "hint": "Paste into Claude Code / Cursor mcp.json, or OpenCode opencode.jsonc. Restart client after mode change.",
        }

    def _api_graph(self) -> Dict[str, Any]:
        omem = self.omem
        assert omem is not None
        try:
            entities = omem.entities()
        except Exception:
            entities = []
        nodes = [
            {
                "id": e["entity"] if isinstance(e, dict) else str(e),
                "type": e.get("type", "CONCEPT") if isinstance(e, dict) else "CONCEPT",
                "count": e.get("count", 1) if isinstance(e, dict) else 1,
            }
            for e in entities
        ]
        edges: list = []
        try:
            entity_names = [n["id"] for n in nodes]
            mems = omem.all(include_inactive=False)
            for mem in mems:
                content = mem.content.lower()
                present = [n for n in entity_names if n.lower() in content]
                for i, a in enumerate(present):
                    for b in present[i + 1 :]:
                        edges.append({"source": a, "target": b})
        except Exception:
            pass
        return {"nodes": nodes, "edges": edges}


def serve(
    omem: Optional[OMem] = None,
    port: int = 7900,
    open_browser: bool = True,
    host: str = "127.0.0.1",
    session_id: Optional[str] = None,
):
    """Start the OMem dashboard server (loopback by default)."""
    DashboardHandler.omem = omem or OMem()
    DashboardHandler.session_id = session_id or os.environ.get("OMEM_SESSION") or "dashboard"
    DashboardHandler.namespace = os.environ.get("OMEM_NS", "default") or "default"
    DashboardHandler.play_writes = os.environ.get("OMEM_OBSERVE_ALLOW_MUTATE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if host in ("", "0.0.0.0", "::"):
        logging.getLogger(__name__).warning(
            "Observe dashboard binding to %s with no auth — local/dev only",
            host or "0.0.0.0",
        )

    with socketserver.TCPServer((host, port), DashboardHandler) as httpd:
        httpd.allow_reuse_address = True
        display = "localhost" if host in ("127.0.0.1", "::1", "localhost") else host
        url = f"http://{display}:{port}"
        print(f"OMem Dashboard running at {url}")
        print("  Prove · Recall · Memory · Tools · MCP · Settings · Graph")

        if open_browser:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard stopped.")


if __name__ == "__main__":
    serve()
