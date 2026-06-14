#!/usr/bin/env python3
"""Add live stage + knowledge graph JS to dashboard (v2, no print issues)."""

import sys

sys.stdout.reconfigure(encoding="utf-8")

with open("company/chairman_dashboard.html", encoding="utf-8") as f:
    c = f.read()

idx = c.find("function collapseAllDepts()")
end = c.find("\n\nfunction addLog", idx)
if end < 0:
    end = c.find("\n\nfunction", idx + 300)
print(f"collapseAllDepts: {idx} -> {end}")

stage_js = """

// ============ View Mode Toggle (Grid vs Stage) ============
let viewMode = 'grid';

function setViewMode(mode) {
  viewMode = mode;
  var gv = document.getElementById('btnGridView');
  var sv = document.getElementById('btnStageView');
  if (gv) gv.classList.toggle('active', mode === 'grid');
  if (sv) sv.classList.toggle('active', mode === 'stage');
  document.getElementById('gridView').style.display = mode === 'grid' ? '' : 'none';
  var stageEl = document.getElementById('stageView');
  if (mode === 'stage') { stageEl.classList.add('active'); renderLiveStage(); }
  else { stageEl.classList.remove('active'); }
}

function renderLiveStage() {
  var stage = document.getElementById('stageCharacters');
  if (!stage) return;
  stage.innerHTML = departments.map(function(d) {
    var color = DEPT_COLORS[d.id] || '#888';
    var st = d.status || 'waiting';
    var deptData = DEPT_AGENTS[d.id];
    var emoji = (deptData && deptData.head) ? deptData.head.emoji : '\\U0001f4c1';
    var name = d.name || d.id;
    return '<div class=\"stage-char ' + st + '\" onclick=\"toggleDept(\\'' + escHtml(d.id) + '\\',0);setViewMode(\\'grid\\');\" title=\"' + escHtml(name) + '\">' +
      '<div class=\"char-sprite\" style=\"color:' + color + ';\">' + emoji + '</div>' +
      '<div class=\"char-name\">' + escHtml(name) + '</div>' +
      '<div class=\"char-dot\"></div>' +
      '</div>';
  }).join('');
}

// ============ Knowledge Graph (vis.js interactive) ============
let kgNetwork = null;

function showKnowledgeGraph() {
  document.getElementById('kgModal').classList.add('active');
  setTimeout(buildKnowledgeGraph, 200);
}

function buildKnowledgeGraph() {
  var container = document.getElementById('kgContainer');
  if (!container || typeof vis === 'undefined') return;

  var nodes = new vis.DataSet([
    {id: 0, label: 'CEO', group: 'ceo', value: 30, shape: 'star'},
    {id: 1, label: 'Strategy', group: 'dept', value: 20},
    {id: 2, label: 'Academic', group: 'dept', value: 20},
    {id: 3, label: 'Sentiment', group: 'dept', value: 18},
    {id: 4, label: 'Data Eng', group: 'dept', value: 22},
    {id: 5, label: 'Backtest', group: 'dept', value: 18},
    {id: 6, label: 'Risk Mgmt', group: 'dept', value: 20},
    {id: 7, label: 'Execution', group: 'dept', value: 16},
    {id: 8, label: 'OpenSrc', group: 'dept', value: 18},
    {id: 9, label: 'IT Tech', group: 'dept', value: 22},
    {id: 10, label: 'Reporting', group: 'dept', value: 14},
    {id: 11, label: 'ExtremeDrive', group: 'guard', value: 18},
    {id: 12, label: 'Evolution', group: 'guard', value: 18},
    {id: 13, label: 'Secretariat', group: 'dept', value: 16},
    {id: 14, label: 'Knowledge', group: 'dept', value: 16},
    {id: 15, label: 'OS-First', group: 'guard', value: 18},
    {id: 100, label: 'OpenBB+Parquet', group: 'tech', value: 12},
    {id: 101, label: 'Qlib', group: 'tech', value: 12},
    {id: 102, label: 'FinBERT+PRAW', group: 'tech', value: 12},
    {id: 103, label: 'NautilusTrader', group: 'tech', value: 14},
    {id: 104, label: 'Riskfolio-Lib', group: 'tech', value: 12},
    {id: 105, label: 'Dagster+Cron', group: 'tech', value: 14},
    {id: 106, label: 'Alphalens', group: 'tech', value: 10},
    {id: 107, label: 'TimescaleDB', group: 'tech', value: 12},
    {id: 108, label: 'FastAPI+SSE', group: 'tech', value: 10},
  ]);

  var edges = new vis.DataSet([
    {from: 0, to: 1}, {from: 0, to: 2}, {from: 0, to: 3}, {from: 0, to: 4},
    {from: 0, to: 5}, {from: 0, to: 6}, {from: 0, to: 7}, {from: 0, to: 8},
    {from: 0, to: 9}, {from: 0, to: 10}, {from: 0, to: 11}, {from: 0, to: 12},
    {from: 0, to: 13}, {from: 0, to: 14}, {from: 0, to: 15},
    {from: 4, to: 100}, {from: 4, to: 107}, {from: 1, to: 101}, {from: 1, to: 106},
    {from: 3, to: 102}, {from: 5, to: 103}, {from: 6, to: 104},
    {from: 9, to: 108}, {from: 9, to: 105}, {from: 12, to: 105},
  ]);

  var data = {nodes: nodes, edges: edges};
  var options = {
    groups: {
      ceo: {color: {background: '#f0b90b', border: '#f0b90b'}, font: {color: '#000', size: 16}},
      dept: {color: {background: '#3b82f6', border: '#2563eb'}, font: {color: '#e2e8f0', size: 14}},
      guard: {color: {background: '#ef4444', border: '#dc2626'}, font: {color: '#fff', size: 14}},
      tech: {color: {background: '#6366f1', border: '#4f46e5'}, font: {color: '#e2e8f0', size: 12}, shape: 'box'},
    },
    edges: {color: {color: '#475569', highlight: '#94a3b8'}, width: 1.5, smooth: {type: 'continuous'}},
    physics: {barnesHut: {gravitationalConstant: -3000, centralGravity: 0.3, springLength: 160}, stabilization: {iterations: 150}},
    interaction: {hover: true, zoomView: true, dragView: true},
  };

  kgNetwork = new vis.Network(container, data, options);
  kgNetwork.on('click', function(params) {
    if (params.nodes.length > 0) {
      var nodeId = params.nodes[0];
      if (nodeId >= 1 && nodeId <= 15) {
        var deptKeys = Object.keys(DEPT_COLORS);
        var deptId = deptKeys[nodeId - 1];
        if (deptId) {
          var d = departments.find(function(dd) { return dd.id === deptId; });
          if (d) {
            document.getElementById('kgModal').classList.remove('active');
            showDeptDetail(deptId, d.name || deptId, d.status || 'waiting', DEPT_COLORS[deptId] || '#888');
          }
        }
      }
    }
  });
}

setTimeout(function() {
  var kgm = document.getElementById('kgModal');
  if (kgm) kgm.addEventListener('click', function(e) { if (e.target === this) this.classList.remove('active'); });
}, 300);
"""

c = c[:end] + stage_js + c[end:]

# Update toggleDept to refresh stage
old_t = "addMilestone("
idx_t = c.find(old_t, end)
if idx_t >= 0:
    line_end = c.find("\n", idx_t)
    old_line = c[idx_t:line_end]
    new_line = old_line + '\n  if (viewMode === "stage") renderLiveStage();'
    c = c.replace(old_line, new_line)
    print("toggleDept stage refresh added")

with open("company/chairman_dashboard.html", "w", encoding="utf-8") as f:
    f.write(c)
print("Done - stage + KG JS added")
