"""OMem Memory Dashboard — zero-dependency web visualization.

Serves a single-page web app that shows:
- Memory graph (cluster visualization)
- Memory timeline
- Namespace browser
- Live retrieval inspector

Run: python -m omem.observe.dashboard.server
Or:  omem dashboard
"""

import http.server
import json
import logging
import socketserver
import threading
import webbrowser
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ...api import OMem

logger = logging.getLogger(__name__)

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OMem — Memory Dashboard</title>
<style>
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg: #0a0a0f; --surface: #12121a; --surface2: #1a1a2e;
  --accent: #7c3aed; --accent2: #06b6d4; --accent3: #f59e0b;
  --text: #e2e8f0; --text2: #94a3b8; --border: #1e293b;
  --green: #10b981; --red: #ef4444; --blue: #3b82f6;
}
body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
       background: var(--bg); color: var(--text); min-height: 100vh; }
.header { background: linear-gradient(135deg, var(--accent), var(--accent2));
           padding: 1.5rem 2rem; display: flex; align-items: center; gap: 1rem; }
.header h1 { font-size: 1.5rem; font-weight: 700; }
.header .badge { background: rgba(255,255,255,0.2); padding: 0.25rem 0.75rem;
                  border-radius: 999px; font-size: 0.75rem; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;
        padding: 1.5rem; max-width: 1400px; margin: 0 auto; }
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: 12px; padding: 1.25rem; }
.card h2 { font-size: 0.9rem; color: var(--accent2); text-transform: uppercase;
           letter-spacing: 0.05em; margin-bottom: 1rem; }
.card.full { grid-column: 1 / -1; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { text-align: left; color: var(--text2); padding: 0.5rem; border-bottom: 1px solid var(--border); }
td { padding: 0.5rem; border-bottom: 1px solid var(--border); vertical-align: top; }
.type-badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 6px;
              font-size: 0.7rem; font-weight: 600; }
.type-SEMANTIC { background: #1e3a5f; color: #60a5fa; }
.type-EPISODIC { background: #3b1f4e; color: #c084fc; }
.type-DECISION { background: #422006; color: #fbbf24; }
.type-CAUSAL { background: #14332e; color: #34d399; }
.type-PROCEDURAL { background: #1c1917; color: #fca5a5; }
.type-WORKING { background: #1e293b; color: #94a3b8; }
.type-ACTIVE { background: #450a0a; color: #f87171; }
.type-REFLECTION { background: #0c4a6e; color: #38bdf8; }
.stat { text-align: center; }
.stat .num { font-size: 2rem; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2));
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.stat .label { font-size: 0.75rem; color: var(--text2); margin-top: 0.25rem; }
.stats-row { display: flex; gap: 1.5rem; justify-content: space-around; flex-wrap: wrap; }
#search { width: 100%; padding: 0.75rem 1rem; background: var(--surface2); border: 1px solid var(--border);
          border-radius: 8px; color: var(--text); font-size: 0.9rem; margin-bottom: 1rem; }
#search:focus { outline: none; border-color: var(--accent); }
.imp-bar { display: inline-block; height: 6px; border-radius: 3px; background: var(--accent); }
.score { color: var(--green); font-weight: 600; }
.inactive { opacity: 0.4; }
button { background: var(--accent); color: white; border: none; padding: 0.5rem 1rem;
         border-radius: 8px; cursor: pointer; font-size: 0.85rem; transition: 0.2s; }
button:hover { opacity: 0.85; transform: translateY(-1px); }
.actions { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.cluster { background: var(--surface2); border-radius: 8px; padding: 0.75rem; margin-bottom: 0.75rem; }
.cluster-header { font-weight: 600; color: var(--accent2); font-size: 0.85rem; margin-bottom: 0.5rem; }
.ns-badge { background: var(--surface2); padding: 0.2rem 0.5rem; border-radius: 4px;
            font-size: 0.7rem; color: var(--accent3); }
#inspect-results { font-family: 'Fira Code', monospace; font-size: 0.8rem; white-space: pre-wrap;
                   background: var(--surface2); padding: 1rem; border-radius: 8px; max-height: 300px;
                   overflow-y: auto; color: var(--text2); }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
.card { animation: fadeIn 0.3s ease; }
.tabs { display: flex; gap: 0; margin-bottom: 0; border-bottom: 1px solid var(--border); }
.tab-btn { background: transparent; color: var(--text2); border: none; border-bottom: 2px solid transparent;
           padding: 0.6rem 1.25rem; cursor: pointer; font-size: 0.85rem; margin-bottom: -1px; border-radius: 0; }
.tab-btn.active { color: var(--accent2); border-bottom-color: var(--accent2); }
.tab-btn:hover { color: var(--text); opacity: 1; transform: none; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
#graph-svg { width: 100%; height: 420px; background: var(--surface2); border-radius: 8px; }
.node circle { stroke: var(--border); stroke-width: 1.5; cursor: pointer; }
.node text { font-size: 11px; fill: var(--text2); pointer-events: none; }
.link { stroke: var(--border); stroke-opacity: 0.5; }
#graph-info { font-size: 0.8rem; color: var(--text2); margin-top: 0.5rem; min-height: 1.5rem; }
</style>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body>
<div class="header">
  <h1>OMem Dashboard</h1>
  <span class="badge">Local preview</span>
  <span class="badge" id="mem-count">—</span>
</div>
<div class="grid">
  <div class="card full">
    <h2>Overview</h2>
    <div class="stats-row" id="stats-row"></div>
  </div>
  <div class="card">
    <h2>Query Inspector</h2>
    <input id="search" placeholder="Type a query to inspect retrieval scoring..." />
    <div id="inspect-results">Enter a query above to see score breakdowns.</div>
  </div>
  <div class="card">
    <h2>Actions</h2>
    <div class="actions">
      <button onclick="doCompress()">Compress</button>
      <button onclick="doReflect()">Reflect</button>
      <button onclick="doDecay()">Decay</button>
      <button onclick="refresh()">Refresh</button>
    </div>
    <div id="action-log" style="font-size:0.8rem;color:var(--text2);max-height:200px;overflow-y:auto;"></div>
  </div>
  <div class="card full">
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('memory-table')">Memory Table</button>
      <button class="tab-btn" onclick="switchTab('knowledge-graph')">Knowledge Graph</button>
    </div>
    <div id="tab-memory-table" class="tab-panel active" style="padding-top:1rem">
      <table>
        <thead><tr><th>ID</th><th>Type</th><th>Content</th><th>Importance</th><th>Accessed</th><th>Namespace</th><th>Source</th></tr></thead>
        <tbody id="mem-table"></tbody>
      </table>
    </div>
    <div id="tab-knowledge-graph" class="tab-panel" style="padding-top:1rem">
      <svg id="graph-svg"></svg>
      <div id="graph-info">Click a node to see related memories.</div>
    </div>
  </div>
</div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const API = '';
async function fetchJSON(url) { const r = await fetch(API + url); return r.json(); }
async function postJSON(url) { const r = await fetch(API + url, {method:'POST'}); return r.json(); }

async function refresh() {
  const stats = await fetchJSON('/api/stats');
  document.getElementById('mem-count').textContent = stats.total + ' memories';
  const sr = document.getElementById('stats-row');
  sr.innerHTML = `
    <div class="stat"><div class="num">${stats.total}</div><div class="label">Active</div></div>
    <div class="stat"><div class="num">${stats.inactive}</div><div class="label">Inactive</div></div>
    <div class="stat"><div class="num">${stats.graph_edges}</div><div class="label">Graph Edges</div></div>
    <div class="stat"><div class="num">${stats.avg_importance.toFixed(2)}</div><div class="label">Avg Importance</div></div>
    <div class="stat"><div class="num">${stats.namespaces.length}</div><div class="label">Namespaces</div></div>
    <div class="stat"><div class="num">${Object.keys(stats.types).length}</div><div class="label">Types</div></div>
  `;
  const mems = await fetchJSON('/api/memories');
  const tb = document.getElementById('mem-table');
  tb.innerHTML = mems.map(m => `
    <tr class="${m.active ? '' : 'inactive'}">
      <td><code>${m.id}</code></td>
      <td><span class="type-badge type-${m.type}">${m.type}</span></td>
      <td>${m.content.substring(0, 100)}${m.content.length > 100 ? '...' : ''}</td>
      <td><div class="imp-bar" style="width:${m.importance*60}px"></div> ${m.importance.toFixed(2)}</td>
      <td>${m.access_count}x</td>
      <td><span class="ns-badge">${m.namespace}</span></td>
      <td>${m.source || '-'}</td>
    </tr>
  `).join('');
}

let searchTimeout;
document.getElementById('search').addEventListener('input', function() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(async () => {
    const q = this.value.trim();
    if (!q) { document.getElementById('inspect-results').textContent = 'Enter a query above.'; return; }
    const data = await fetchJSON('/api/inspect?q=' + encodeURIComponent(q));
    document.getElementById('inspect-results').textContent = data.map(e =>
      `Memory ${e.memory_id} — score ${e.final_score.toFixed(4)}\\n` +
      `  vector:     ${e.vector_score.toFixed(4)}\\n` +
      `  keyword:    ${e.keyword_score.toFixed(4)}  ${JSON.stringify(e.matched_keywords)}\\n` +
      `  importance: ${e.importance_score.toFixed(4)}\\n` +
      `  recency:    ${e.recency_score.toFixed(4)}\\n` +
      `  frequency:  ${e.frequency_bonus.toFixed(4)}`
    ).join('\\n\\n') || 'No results.';
  }, 300);
});

function log(msg) {
  const el = document.getElementById('action-log');
  el.textContent = new Date().toLocaleTimeString() + ' — ' + msg + '\\n' + el.textContent;
}
async function doCompress() { const r = await postJSON('/api/compress'); log('Compressed: ' + JSON.stringify(r)); refresh(); }
async function doReflect() { const r = await postJSON('/api/reflect'); log('Reflected: ' + r.length + ' insights'); refresh(); }
async function doDecay() { const r = await postJSON('/api/decay'); log('Decayed: ' + r.length + ' memories'); refresh(); }

refresh();
setInterval(refresh, 5000);

// --- Tab switching ---
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => {
    b.classList.toggle('active', b.getAttribute('onclick').includes(name));
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + name);
  });
  if (name === 'knowledge-graph') loadGraph();
}

// --- Knowledge Graph (D3 force-directed) ---
const TYPE_COLORS = {
  PERSON: '#3b82f6', TECHNOLOGY: '#8b5cf6', PROJECT: '#10b981',
  ORGANIZATION: '#f59e0b', LOCATION: '#ef4444', CONCEPT: '#06b6d4',
  default: '#94a3b8'
};

let graphLoaded = false;

async function loadGraph() {
  if (graphLoaded) return;
  const data = await fetchJSON('/api/graph');
  if (!data.nodes || data.nodes.length === 0) {
    document.getElementById('graph-info').textContent = 'No entities in the knowledge graph yet. Add some memories first.';
    return;
  }
  graphLoaded = true;
  renderGraph(data);
}

function renderGraph(data) {
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();
  const rect = document.getElementById('graph-svg').getBoundingClientRect();
  const W = rect.width || 800, H = rect.height || 420;
  svg.attr('viewBox', `0 0 ${W} ${H}`);

  const simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges).id(d => d.id).distance(90))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(30));

  const link = svg.append('g').selectAll('line')
    .data(data.edges).join('line').attr('class', 'link');

  const node = svg.append('g').selectAll('g')
    .data(data.nodes).join('g').attr('class', 'node')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }))
    .on('click', async (e, d) => {
      document.getElementById('graph-info').textContent = 'Loading memories for: ' + d.id + '...';
      const related = await fetchJSON('/api/inspect?q=' + encodeURIComponent(d.id));
      const info = related.length
        ? related.slice(0, 3).map(r => 'score ' + r.final_score.toFixed(3) + ': mem ' + r.memory_id).join(' | ')
        : 'No memories found for this entity.';
      document.getElementById('graph-info').textContent = d.id + ' (' + (d.type || 'entity') + ', ' + (d.count || 0) + ' refs): ' + info;
    });

  node.append('circle')
    .attr('r', d => Math.min(8 + (d.count || 1) * 2, 22))
    .attr('fill', d => TYPE_COLORS[d.type] || TYPE_COLORS.default);

  node.append('text')
    .attr('dy', d => -(Math.min(8 + (d.count || 1) * 2, 22) + 4))
    .attr('text-anchor', 'middle')
    .text(d => d.id.length > 16 ? d.id.slice(0, 14) + '…' : d.id);

  simulation.on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}
</script>
</body>
</html>"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the OMem dashboard."""

    omem: Optional[OMem] = None

    def log_message(self, format, *args):
        pass  # suppress logs

    def _send(self, data, content_type="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if isinstance(data, str):
            self.wfile.write(data.encode())
        else:
            self.wfile.write(json.dumps(data, default=str).encode())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send(_HTML, "text/html")
        elif path == "/api/stats":
            self._send(self.omem.stats())
        elif path == "/api/memories":
            mems = self.omem.all(include_inactive=True)
            self._send([m.to_dict() for m in mems])
        elif path == "/api/inspect":
            q = params.get("q", [""])[0]
            exps = self.omem.inspect(q, top_k=10)
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
            results = self.omem.recall(q, top_k=10)
            self._send([m.to_dict() for m in results])
        elif path == "/api/graph":
            try:
                entities = self.omem.entities()
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
            # Build co-occurrence edges from shared memory references
            edges: list = []
            try:
                entity_names = [n["id"] for n in nodes]
                mems = self.omem.all(include_inactive=False)
                for mem in mems:
                    content = mem.content.lower()
                    present = [n for n in entity_names if n.lower() in content]
                    for i, a in enumerate(present):
                        for b in present[i + 1:]:
                            edges.append({"source": a, "target": b})
            except Exception:
                pass
            self._send({"nodes": nodes, "edges": edges})
        else:
            self._send({"error": "not found"}, code=404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/compress":
            result = self.omem.compress()
            self._send(result)
        elif path == "/api/reflect":
            refs = self.omem.reflect()
            self._send([m.to_dict() for m in refs])
        elif path == "/api/decay":
            ids = self.omem.decay()
            self._send(ids)
        else:
            self._send({"error": "not found"}, code=404)


def serve(omem: Optional[OMem] = None, port: int = 7900, open_browser: bool = True):
    """Start the OMem dashboard server."""
    DashboardHandler.omem = omem or OMem()

    with socketserver.TCPServer(("", port), DashboardHandler) as httpd:
        httpd.allow_reuse_address = True
        url = f"http://localhost:{port}"
        print(f"OMem Dashboard running at {url}")

        if open_browser:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard stopped.")


if __name__ == "__main__":
    serve()
