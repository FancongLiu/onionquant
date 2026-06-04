#!/usr/bin/env python3
"""Add anime game-like Live Stage + vis.js Knowledge Graph to dashboard."""

with open('company/chairman_dashboard.html', 'r', encoding='utf-8') as f:
    c = f.read()

changes = 0

# ==== 1. Add vis.js CDN alongside mermaid ====
old_cdn = '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>'
new_cdn = '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.6/dist/vis-network.min.js"></script>'
if old_cdn in c:
    c = c.replace(old_cdn, new_cdn)
    changes += 1
    print("1. vis.js CDN added")

# ==== 2. Add CSS for Live Stage (anime game-like) ====
old_css_section = '/* ─── Compact Department Grid ─── */'
new_css_block = '''/* ─── View Toggle ─── */
.view-toggle { display: flex; gap: 4px; }
.view-toggle button {
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px;
  color: var(--muted); cursor: pointer; font-size: 0.7em; padding: 4px 10px; transition: all 0.2s;
}
.view-toggle button.active { border-color: var(--gold); color: var(--gold); background: rgba(240,185,11,0.08); }
.view-toggle button:hover { border-color: var(--accent); }

/* ─── Live Stage (Anime Game-like) ─── */
.live-stage { display: none; position: relative; min-height: 300px; background: linear-gradient(180deg, rgba(10,14,23,0.9) 0%, rgba(17,24,39,0.6) 50%, rgba(10,14,23,0.9) 100%); border: 1px solid var(--border); border-radius: 14px; padding: 20px; overflow: hidden; }
.live-stage.active { display: block; }
.stage-floor { position: absolute; bottom: 0; left: 0; right: 0; height: 40px; background: linear-gradient(0deg, rgba(59,130,246,0.05) 0%, transparent 100%); border-top: 1px solid rgba(59,130,246,0.1); }
.stage-characters { display: flex; flex-wrap: wrap; gap: 14px; justify-content: center; align-items: flex-end; padding-bottom: 30px; position: relative; z-index: 2; }
.stage-char {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  transition: all 0.3s ease; cursor: pointer; position: relative;
}
.stage-char .char-sprite {
  font-size: 3em; transition: all 0.3s ease; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
  position: relative;
}
/* Animation: working = bouncing */
.stage-char.working .char-sprite {
  animation: charBounce 0.6s ease-in-out infinite;
  filter: drop-shadow(0 0 12px rgba(16,185,129,0.6)) drop-shadow(0 2px 4px rgba(0,0,0,0.5));
}
@keyframes charBounce {
  0%,100% { transform: translateY(0) scale(1); }
  30% { transform: translateY(-16px) scale(1.08); }
  50% { transform: translateY(-6px) scale(1.02); }
  70% { transform: translateY(-22px) scale(1.05); }
}
/* Animation: thinking = slow pulse */
.stage-char.thinking .char-sprite {
  animation: charPulse 2s ease-in-out infinite;
  filter: drop-shadow(0 0 8px rgba(245,158,11,0.4)) drop-shadow(0 2px 4px rgba(0,0,0,0.5));
}
@keyframes charPulse {
  0%,100% { transform: scale(1); opacity: 0.9; }
  50% { transform: scale(1.06); opacity: 1; }
}
/* Animation: waiting = subtle idle */
.stage-char.waiting .char-sprite {
  animation: charIdle 4s ease-in-out infinite;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
  opacity: 0.65;
}
@keyframes charIdle {
  0%,100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
/* Character name label */
.stage-char .char-name {
  font-size: 0.62em; color: var(--muted); font-weight: 600; text-align: center;
  max-width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.stage-char.working .char-name { color: var(--green); }
.stage-char.thinking .char-name { color: #f59e0b; }
/* Activity indicator dot */
.stage-char .char-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--muted);
  transition: all 0.3s;
}
.stage-char.working .char-dot { background: var(--green); box-shadow: 0 0 8px var(--green); }
.stage-char.thinking .char-dot { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
/* Working departments come to front */
.stage-char.working { z-index: 10; order: -1; }
.stage-char.thinking { z-index: 5; order: 0; }

/* ─── Knowledge Graph Panel ─── */
.kg-modal-content { max-width: 95vw !important; width: 1100px !important; }
.kg-container { width: 100%; height: 65vh; border: 1px solid var(--border); border-radius: 10px; background: var(--bg); }

/* ─── Compact Department Grid ─── */'''

if old_css_section in c:
    c = c.replace(old_css_section, new_css_block)
    changes += 1
    print("2. Live Stage + Knowledge Graph CSS added")

# ==== 3. Add view toggle and live stage HTML ====
old_dept_section = '<!-- Department Compact Grid -->'
new_dept_section = '''<!-- View Toggle & Department Section -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <span class="section-title" style="margin-bottom:0;">\U0001f3e2 16 部门 · 组织架构</span>
        <div class="view-toggle">
          <button id="btnGridView" class="active" onclick="setViewMode('grid')">\U0001f5b1️ 网格</button>
          <button id="btnStageView" onclick="setViewMode('stage')">\U0001f3ae 舞台</button>
          <button onclick="showKnowledgeGraph()" style="background:linear-gradient(135deg,#8b5cf6,#6366f1);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:0.68em;padding:4px 8px;">\U0001f578️ 知识图谱</button>
        </div>
      </div>
      <!-- Grid View -->
      <div id="gridView"><div class="dept-compact-grid" id="deptGrid"></div><div id="orgTreePanel"></div></div>
      <!-- Live Stage View -->
      <div class="live-stage" id="stageView">
        <div class="stage-characters" id="stageCharacters"></div>
        <div class="stage-floor"></div>
      </div>
      <!-- Original (hidden) -->'''

# Actually, let me just replace the entire department section HTML
old = '<!-- Department Compact Grid -->'
if old in c:
    start = c.find(old)
    end = c.find('<!-- Sidebar -->', start)
    if start >= 0 and end >= 0:
        new_html = '''<!-- View Toggle & Departments -->
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <span class="section-title" style="margin-bottom:0;">\U0001f3e2 16 部门 · 组织架构 (点击查看)</span>
          <div style="display:flex;gap:6px;">
            <div class="view-toggle">
              <button id="btnGridView" class="active" onclick="setViewMode('grid')">\U0001f5b1️ 网格</button>
              <button id="btnStageView" onclick="setViewMode('stage')">\U0001f3ae 舞台</button>
            </div>
            <button onclick="showKnowledgeGraph()" style="background:linear-gradient(135deg,#8b5cf6,#6366f1);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:0.68em;padding:4px 10px;">\U0001f578️ 知识图谱</button>
            <button onclick="expandAllDepts()" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);cursor:pointer;font-size:0.68em;padding:3px 8px;">\U0001f53d</button>
            <button onclick="collapseAllDepts()" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);cursor:pointer;font-size:0.68em;padding:3px 8px;">\U0001f53c</button>
          </div>
        </div>
        <!-- Grid View -->
        <div id="gridView"><div class="dept-compact-grid" id="deptGrid"></div><div id="orgTreePanel"></div></div>
        <!-- Live Stage View -->
        <div class="live-stage" id="stageView">
          <div class="stage-characters" id="stageCharacters"></div>
          <div class="stage-floor"></div>
        </div>
      </div>

      '''
        c = c[:start] + new_html + c[end:]
        changes += 1
        print("3. View toggle + live stage HTML added")

# ==== 4. Add Knowledge Graph Modal HTML ====
old_kg_marker = '<!-- Department Detail Modal -->'
new_kg_modal = '''<!-- Knowledge Graph Modal -->
<div class="modal-overlay" id="kgModal">
  <div class="modal-content kg-modal-content">
    <button class="modal-close" onclick="document.getElementById('kgModal').classList.remove('active')">✕</button>
    <h3 style="color:var(--gold);margin-bottom:10px;">\U0001f578️ OnionQuant · 知识图谱 (Knowledge Graph)</h3>
    <div class="kg-container" id="kgContainer"></div>
    <div style="font-size:0.7em;color:var(--muted);margin-top:6px;">\U0001f446 拖动节点 · 滚轮缩放 · 点击查看详情 · 16部门 + 技术栈关联</div>
  </div>
</div>

<!-- Department Detail Modal -->'''

if old_kg_marker in c:
    c = c.replace(old_kg_marker, new_kg_modal)
    changes += 1
    print("4. Knowledge Graph modal added")

# ==== 5. Add JS functions for stage view and knowledge graph ====
# Add after collapseAllDepts
old_collapse = """function collapseAllDepts() {
  expandedDept = null;
  renderDepts();
  addMilestone('\U0001f4d6', '全部折叠部门', '');
}"""

new_stage_js = """function collapseAllDepts() {
  expandedDept = null;
  renderDepts();
  addMilestone('\U0001f4d6', '全部折叠部门', '');
}

// ============ View Mode Toggle ============
let viewMode = 'grid';

function setViewMode(mode) {
  viewMode = mode;
  document.getElementById('btnGridView').classList.toggle('active', mode === 'grid');
  document.getElementById('btnStageView').classList.toggle('active', mode === 'stage');
  document.getElementById('gridView').style.display = mode === 'grid' ? '' : 'none';
  document.getElementById('stageView').classList.toggle('active', mode === 'stage');
  if (mode === 'stage') renderLiveStage();
}

function renderLiveStage() {
  const stage = document.getElementById('stageCharacters');
  stage.innerHTML = departments.map(d => {
    const color = DEPT_COLORS[d.id] || '#888';
    const st = d.status || 'waiting';
    const deptData = DEPT_AGENTS[d.id];
    const emoji = deptData?.head?.emoji || '\U0001f4c1';
    const name = d.name || d.id;
    return `<div class="stage-char ${st}" onclick="toggleDept('${escHtml(d.id)}',0);setViewMode('grid');" title="${escHtml(name)} — ${st}">
      <div class="char-sprite" style="color:${color};">${emoji}</div>
      <div class="char-name">${escHtml(name)}</div>
      <div class="char-dot"></div>
    </div>`;
  }).join('');
  addMilestone('\U0001f3ae', '切换舞台视图', '');
}

// ============ Knowledge Graph (vis.js) ============
let kgNetwork = null;

function showKnowledgeGraph() {
  document.getElementById('kgModal').classList.add('active');
  setTimeout(buildKnowledgeGraph, 200);
}

function buildKnowledgeGraph() {
  const container = document.getElementById('kgContainer');
  if (!container) return;

  // Nodes: CEO + Departments + Tech Stack
  const nodes = new vis.DataSet([
    {id: 0, label: '\U0001f3af CEO', group: 'ceo', value: 30, shape: 'star', color: {background:'#f0b90b',border:'#f0b90b',highlight:{background:'#f59e0b',border:'#f59e0b'}}},
    {id: 1, label: '\U0001f4ca 策略研究部', group: 'dept', value: 20},
    {id: 2, label: '\U0001f393 学术研究部', group: 'dept', value: 20},
    {id: 3, label: '\U0001f4f0 舆情情报部', group: 'dept', value: 18},
    {id: 4, label: '\U0001f4be 数据工程部', group: 'dept', value: 22},
    {id: 5, label: '⚡ 回测引擎部', group: 'dept', value: 18},
    {id: 6, label: '\U0001f6e1️ 风险管理部', group: 'dept', value: 20},
    {id: 7, label: '\U0001f4b0 交易执行部', group: 'dept', value: 16},
    {id: 8, label: '\U0001f50d 开源研究院', group: 'dept', value: 18},
    {id: 9, label: '\U0001f4bb IT技术部', group: 'dept', value: 22},
    {id: 10, label: '\U0001f4ca 汇报展示部', group: 'dept', value: 14},
    {id: 11, label: '⚔️ 极限驱动部', group: 'guard', value: 18},
    {id: 12, label: '\U0001f525 持续进化部', group: 'guard', value: 18},
    {id: 13, label: '\U0001f4cb 秘书处', group: 'dept', value: 16},
    {id: 14, label: '\U0001f52e 知识管理部', group: 'dept', value: 16},
    {id: 15, label: '\U0001f6ab 开源优先部', group: 'guard', value: 18},
    {id: 100, label: '\U0001f4e6 OpenBB+Parquet', group: 'tech', value: 12},
    {id: 101, label: '\U0001f9e0 Qlib', group: 'tech', value: 12},
    {id: 102, label: '\U0001f4f0 FinBERT+PRAW', group: 'tech', value: 12},
    {id: 103, label: '\U0001f680 NautilusTrader', group: 'tech', value: 14},
    {id: 104, label: '\U0001f6e1️ Riskfolio-Lib', group: 'tech', value: 12},
    {id: 105, label: '\U0001f504 Dagster+Cron', group: 'tech', value: 14},
    {id: 106, label: '\U0001f4ca Alphalens', group: 'tech', value: 10},
    {id: 107, label: '\U0001f4be TimescaleDB', group: 'tech', value: 12},
    {id: 108, label: '⚙️ FastAPI+SSE', group: 'tech', value: 10},
  ]);

  // Edges
  const edges = new vis.DataSet([
    {from: 0, to: 1}, {from: 0, to: 2}, {from: 0, to: 3}, {from: 0, to: 4},
    {from: 0, to: 5}, {from: 0, to: 6}, {from: 0, to: 7}, {from: 0, to: 8},
    {from: 0, to: 9}, {from: 0, to: 10}, {from: 0, to: 11}, {from: 0, to: 12},
    {from: 0, to: 13}, {from: 0, to: 14}, {from: 0, to: 15},
    {from: 4, to: 100}, {from: 4, to: 107},
    {from: 1, to: 101}, {from: 1, to: 106},
    {from: 3, to: 102},
    {from: 5, to: 103},
    {from: 6, to: 104},
    {from: 9, to: 108}, {from: 9, to: 105},
    {from: 12, to: 105},
  ]);

  const data = {nodes, edges};
  const options = {
    groups: {
      ceo: {color: {background: '#f0b90b', border: '#f0b90b', highlight: {background: '#f59e0b', border: '#f59e0b'}}, font: {color: '#000', size: 16, face: 'Microsoft YaHei'}},
      dept: {color: {background: '#3b82f6', border: '#2563eb', highlight: {background: '#60a5fa', border: '#3b82f6'}}, font: {color: '#e2e8f0', size: 14, face: 'Microsoft YaHei'}},
      guard: {color: {background: '#ef4444', border: '#dc2626', highlight: {background: '#f87171', border: '#ef4444'}}, font: {color: '#fff', size: 14, face: 'Microsoft YaHei'}},
      tech: {color: {background: '#6366f1', border: '#4f46e5', highlight: {background: '#818cf8', border: '#6366f1'}}, font: {color: '#e2e8f0', size: 12, face: 'Microsoft YaHei'}, shape: 'box'},
    },
    edges: {color: {color: '#475569', highlight: '#94a3b8'}, width: 1.5, smooth: {type: 'continuous'}},
    physics: {barnesHut: {gravitationalConstant: -3000, centralGravity: 0.3, springLength: 160, springConstant: 0.04}, stabilization: {iterations: 150}},
    interaction: {hover: true, tooltipDelay: 100, zoomView: true, dragView: true},
  };

  kgNetwork = new vis.Network(container, data, options);
  kgNetwork.on('click', function(params) {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      if (nodeId >= 1 && nodeId <= 15) {
        const deptKeys = Object.keys(DEPT_COLORS);
        const deptId = deptKeys[nodeId - 1];
        if (deptId) {
          const d = departments.find(dd => dd.id === deptId);
          if (d) {
            document.getElementById('kgModal').classList.remove('active');
            showDeptDetail(deptId, d.name || deptId, d.status || 'waiting', DEPT_COLORS[deptId] || '#888');
          }
        }
      }
    }
  });
  addMilestone('\U0001f578️', '知识图谱已打开', 'vis.js交互图谱');
}

// Close KG modal on overlay click
setTimeout(() => {
  const kgm = document.getElementById('kgModal');
  if (kgm) kgm.addEventListener('click', function(e) { if (e.target === this) this.classList.remove('active'); });
}, 300);
"""

if old_collapse in c:
    c = c.replace(old_collapse, old_collapse + '\n\n' + new_stage_js)
    changes += 1
    print("5. Stage view + Knowledge Graph JS added")
else:
    print("5. collapseAllDepts NOT FOUND")

# ==== 6. Update renderDepts to also refresh stage if visible ====
old_render_end = "  if (expandedDept) addMilestone('\\U0001f446', '\\u5c55\\u5f00\\u90e8\\u95e8\\u67b6\\u6784: ', deptId);"
new_render_end = """  if (expandedDept) addMilestone('\U0001f446', '展开部门架构: ', deptId);
  if (viewMode === 'stage') renderLiveStage();"""
if old_render_end in c:
    c = c.replace(old_render_end, new_render_end)
    changes += 1
    print("6. renderDepts stage refresh added")

with open('company/chairman_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(c)

print(f"\n=== Done: {changes} changes ===")
