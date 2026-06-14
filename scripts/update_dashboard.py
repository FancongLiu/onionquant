#!/usr/bin/env python3
"""Apply compact grid, Teams org tree, and zoomable mermaid to chairman_dashboard.html."""

with open("company/chairman_dashboard.html", encoding="utf-8") as f:
    content = f.read()

changes = 0

# ======= 1. Replace Department HTML section =======
old_dept = "<!-- Department Accordion -->"
new_dept = "<!-- Department Compact Grid -->"
if old_dept in content:
    # Find the full section from <!-- Department Accordion --> to the closing </div> before <!-- Sidebar -->
    start = content.find(old_dept)
    end = content.find("<!-- Sidebar -->", start)
    if start >= 0 and end >= 0:
        new_section = """<!-- Department Compact Grid -->
      <div>
        <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>\U0001f3e2 16 部门 · 组织架构 (点击展开查看内部人员)</span>
          <div style="display:flex;gap:6px;">
            <button onclick="expandAllDepts()" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);cursor:pointer;font-size:0.7em;padding:3px 8px;">\U0001f53d 全部展开</button>
            <button onclick="collapseAllDepts()" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--muted);cursor:pointer;font-size:0.7em;padding:3px 8px;">\U0001f53c 全部折叠</button>
          </div>
        </div>
        <div class="dept-compact-grid" id="deptGrid"></div>
        <div id="orgTreePanel"></div>
      </div>

      """
        content = content[:start] + new_section + content[end:]
        changes += 1
        print("1. Department HTML replaced")
else:
    print("1. Department HTML marker not found")

# ======= 2. Replace Architecture Modal HTML =======
old_arch = "<!-- Architecture Modal -->"
if old_arch in content:
    start = content.find(old_arch)
    end = content.find("<!-- Department Detail Modal -->", start)
    if start >= 0 and end >= 0:
        new_modal = """<!-- Architecture Modal (Zoomable) -->
<div class="modal-overlay" id="archModal">
  <div class="modal-content" style="max-width:95vw;width:1100px;">
    <button class="modal-close" onclick="closeArchitecture()">✕</button>
    <h3 style="color:var(--gold);margin-bottom:6px;">\U0001f3d7️ OnionQuant · 系统架构</h3>
    <div class="mermaid-zoom-bar">
      <button onclick="zoomMermaid(-0.2)" title="缩小">\U0001f50d−</button>
      <button onclick="zoomMermaid(0.2)" title="放大">\U0001f50d+</button>
      <button onclick="resetMermaidZoom()" title="重置">\U0001f504 重置</button>
      <span class="zoom-val" id="zoomLevel">100%</span>
      <span style="font-size:0.7em;color:var(--muted);">\U0001f446 支持 Ctrl+滚轮缩放</span>
    </div>
    <div class="mermaid-scroll" id="mermaidScroll">
      <div class="mermaid-diagram" id="archDiagram" style="min-width:800px;min-height:400px;transform-origin:top left;"></div>
    </div>
  </div>
</div>

"""
        content = content[:start] + new_modal + content[end:]
        changes += 1
        print("2. Architecture modal replaced")
else:
    print("2. Architecture modal marker not found")

# ======= 3. Replace renderDepts + toggleDept + expandAllDepts =======
old_func = "// ============ Render Depts (dynamic from API) ============"
if old_func in content:
    start = content.find(old_func)
    # Find next '// ============ ' marker after the expandAllDepts function
    # search for addLog function
    end = content.find("\nfunction addLog", start)
    if end < 0:
        end = content.find("\nfunction escHtml", start)
    if start >= 0 and end >= 0:
        new_funcs = """// ============ Render Depts (Compact Grid + Teams Org Tree) ============
async function fetchDepts() {
  try {
    const r = await fetch('/api/departments');
    if (!r.ok) return;
    const d = await r.json();
    departments = d.departments || [];
    renderDepts();
  } catch(e) {}
}

let expandedDept = null;

function countAgents(deptData) {
  if (!deptData) return 0;
  let n = 1;
  (deptData.teams||[]).forEach(t => { n += 1 + (t.members||[]).length; });
  return n;
}

function statusIcon(s) {
  return s === 'active' ? '\U0001f7e2' : s === 'thinking' ? '\U0001f7e1' : '\\u26aa';
}

function renderDepts() {
  const grid = document.getElementById('deptGrid');
  const treePanel = document.getElementById('orgTreePanel');
  if (!departments.length) { grid.innerHTML = '<div style="color:var(--muted)">\\u52a0\\u8f7d\\u4e2d...</div>'; treePanel.innerHTML=''; return; }
  const labels = {working:'\U0001f535 \\u5de5\\u4f5c\\u4e2d',thinking:'\U0001f7e1 \\u601d\\u8003\\u4e2d',waiting:'\\u26aa \\u5f85\\u547d',done:'\\u2705 \\u5b8c\\u6210'};

  grid.innerHTML = departments.map((d, i) => {
    const color = DEPT_COLORS[d.id] || '#888';
    const st = d.status || 'waiting';
    const deptData = DEPT_AGENTS[d.id];
    const totalAgents = countAgents(deptData);
    const headEmoji = deptData?.head?.emoji || '\U0001f4c1';
    const headName = deptData?.head?.name || '';
    const isOpen = expandedDept === d.id;
    const stIcon = st === 'working' ? '\U0001f7e2' : st === 'thinking' ? '\U0001f7e1' : '\\u26aa';

    return `<div class="dept-compact-card ${isOpen ? 'open' : ''}" id="dept-card-${i}" onclick="toggleDept('${escHtml(d.id)}',${i})" style="border-top:3px solid ${color}">
      <div class="dcc-emoji">${headEmoji}</div>
      <div class="dcc-name">${escHtml(d.name)}</div>
      <div class="dcc-head">${escHtml(headName)}</div>
      <div class="dcc-badges">
        <span class="dcc-badge">${stIcon} ${labels[st]||st}</span>
        <span class="dcc-badge st-green">\U0001f465 ${totalAgents}</span>
        ${d.done ? `<span class="dcc-badge st-green">\\u2705 ${d.done}</span>` : ''}
      </div>
    </div>`;
  }).join('');

  if (expandedDept && expandedDept !== '__all__') {
    const d = departments.find(dd => dd.id === expandedDept);
    if (d) { treePanel.innerHTML = renderOrgTree(d); treePanel.style.display = ''; }
  } else if (expandedDept === '__all__') {
    treePanel.innerHTML = '<div style="display:flex;flex-direction:column;gap:16px;">' + departments.map(d => renderOrgTree(d)).join('') + '</div>';
    treePanel.style.display = '';
  } else {
    treePanel.innerHTML = '';
    treePanel.style.display = 'none';
  }
}

function renderOrgTree(d) {
  const color = DEPT_COLORS[d.id] || '#888';
  const deptData = DEPT_AGENTS[d.id];
  if (!deptData) return `<div style="color:var(--muted);padding:8px;">${escHtml(d.name)}: \\u6682\\u65e0\\u4eba\\u5458\\u6570\\u636e</div>`;

  const head = deptData.head;
  const teams = deptData.teams || [];

  let teamsHtml = '';
  if (teams.length > 0) {
    teamsHtml = '<div class="org-conn"></div><div class="org-teams">';
    teams.forEach(t => {
      const lead = t.lead;
      const members = t.members || [];
      let memsHtml = '';
      if (members.length > 0) {
        memsHtml = '<div class="org-team-mems">' + members.map(m =>
          `<div class="org-node member-node">
            <span class="on-emoji">${m.emoji||'\U0001f465'}</span>
            <div class="on-info"><div class="on-name">${escHtml(m.name)}</div><div class="on-role">${escHtml(m.role)}</div></div>
            <span class="on-st">${statusIcon(m.status)}</span>
          </div>`
        ).join('') + '</div>';
      }
      teamsHtml += `<div class="org-team">
        <div class="org-node lead-node">
          <span class="on-emoji">${lead.emoji||'\U0001f465'}</span>
          <div class="on-info"><div class="on-name">${escHtml(lead.name)}</div><div class="on-role">${escHtml(lead.role)}</div><div class="on-skill">${escHtml(lead.skill)}</div></div>
          <span class="on-st">${statusIcon(lead.status)}</span>
        </div>
        ${memsHtml}
      </div>`;
    });
    teamsHtml += '</div>';
  } else {
    teamsHtml = '<div style="color:var(--muted);font-size:0.7em;padding:8px;">\\u6682\\u65e0\\u5c0f\\u7ec4</div>';
  }

  return `<div class="org-tree-wrap" style="border-left:3px solid ${color}">
    <div style="font-weight:600;font-size:0.8em;margin-bottom:8px;color:var(--gold);">${head?.emoji||''} ${escHtml(d.name)} \\u2014 Teams\\u5f0f\\u7ec4\\u7ec7\\u67b6\\u6784</div>
    <div class="org-tree">
      <div class="org-node head-node">
        <span class="on-emoji">${head?.emoji||'\U0001f451'}</span>
        <div class="on-info"><div class="on-name">${escHtml(head?.name||'')}</div><div class="on-role">${escHtml(head?.role||'')}</div><div class="on-skill">${escHtml(head?.skill||'')}</div></div>
        <span class="on-st" style="color:var(--gold);">\U0001f451 \\u90e8\\u957f</span>
      </div>
      ${teamsHtml}
    </div>
  </div>`;
}

function toggleDept(deptId, idx) {
  if (expandedDept === deptId) { expandedDept = null; }
  else { expandedDept = deptId; }
  renderDepts();
  if (expandedDept) addMilestone('\U0001f446', '\\u5c55\\u5f00\\u90e8\\u95e8\\u67b6\\u6784: ', deptId);
}

function expandAllDepts() {
  expandedDept = '__all__';
  renderDepts();
  addMilestone('\U0001f4d6', '\\u5168\\u90e8\\u5c55\\u5f00\\u90e8\\u95e8\\u67b6\\u6784', '');
}

function collapseAllDepts() {
  expandedDept = null;
  renderDepts();
  addMilestone('\U0001f4d6', '\\u5168\\u90e8\\u6298\\u53e0\\u90e8\\u95e8', '');
}

"""
        content = content[:start] + new_funcs + content[end:]
        changes += 1
        print("3. renderDepts functions replaced")
else:
    print("3. renderDepts marker not found")

# ======= 4. Replace showArchitecture =======
old_show = "// ============ Architecture Modal ============"
if old_show in content:
    start = content.find(old_show)
    # Find next major section marker
    end = content.find("\n// ============ Outbox Expand", start)
    if end < 0:
        end = content.find("\n// ============ Keyboard", start)
    if start >= 0 and end >= 0:
        new_show = """// ============ Architecture Modal (Zoomable Mermaid) ============
let mermaidZoom = 1.0;

function showArchitecture() {
  const mermaidCode = `
graph TD
    CHAIRMAN[\U0001f451 Chairman]
    INBOX[\U0001f4e5 inbox/]
    OUTBOX[\U0001f4e4 outbox/]
    CEO[\U0001f3af CEO Claude]

    CHAIRMAN -->|指令| INBOX
    INBOX -->|读取| CEO
    CEO -->|请示| OUTBOX
    OUTBOX -->|SSE推送| CHAIRMAN

    CEO --> DEPT1[\U0001f4ca 策略研究部]
    CEO --> DEPT2[\U0001f393 学术研究部]
    CEO --> DEPT3[\U0001f4f0 舆情情报部]
    CEO --> DEPT4[\U0001f4be 数据工程部]
    CEO --> DEPT5[⚡ 回测引擎部]
    CEO --> DEPT6[\U0001f6e1️ 风险管理部]
    CEO --> DEPT7[\U0001f4b0 交易执行部]
    CEO --> DEPT8[\U0001f50d 开源研究院]
    CEO --> DEPT9[\U0001f4bb IT技术部]
    CEO --> DEPT10[\U0001f4ca 汇报展示部]
    CEO --> GUARD[⚔️ 极限驱动部]
    CEO --> EVOLVE[\U0001f525 持续进化部]
    CEO --> SECRET[\U0001f4cb 秘书处]
    CEO --> KM[\U0001f52e 知识管理部]
    CEO --> OSF[\U0001f6ab 开源优先部]

    subgraph TECH[技术栈]
        DATA[数据层: OpenBB + Parquet + Polars]
        AI[AI层: Qlib + FinRL-X]
        NLP[NLP层: FinBERT + PRAW]
        BT[回测层: NautilusTrader + Backtrader]
        RISK[风控层: Riskfolio-Lib + pandas-ta]
        EXEC[执行层: IBKR API + Alpaca]
        ORCH[编排层: Dagster + TimescaleDB + Cron]
    end

    CEO --- TECH

    style CHAIRMAN fill:#f0b90b,stroke:#f0b90b,color:#000
    style CEO fill:#3b82f6,stroke:#3b82f6,color:#fff
    style GUARD fill:#ef4444,stroke:#ef4444,color:#fff
    style OSF fill:#ef4444,stroke:#ef4444,color:#fff
    style TECH fill:#1a1f2e,stroke:#555,color:#e2e8f0
  `;

  document.getElementById('archDiagram').innerHTML = '<pre class="mermaid">' + mermaidCode + '</pre>';
  document.getElementById('archModal').classList.add('active');
  mermaidZoom = 1.0;
  updateZoom();
  setTimeout(() => { if (window.mermaid) mermaid.run(); }, 150);
}

function zoomMermaid(delta) {
  mermaidZoom = Math.max(0.3, Math.min(3.0, mermaidZoom + delta));
  updateZoom();
}

function resetMermaidZoom() {
  mermaidZoom = 1.0;
  updateZoom();
}

function updateZoom() {
  const el = document.getElementById('archDiagram');
  if (el) el.style.transform = 'scale(' + mermaidZoom + ')';
  const zl = document.getElementById('zoomLevel');
  if (zl) zl.textContent = Math.round(mermaidZoom * 100) + '%';
}

function closeArchitecture() {
  document.getElementById('archModal').classList.remove('active');
  mermaidZoom = 1.0;
}

"""
        content = content[:start] + new_show + content[end:]
        changes += 1
        print("4. showArchitecture replaced")
else:
    print("4. showArchitecture marker not found")

# ======= 5. Replace showDeptDetail =======
old_detail = "// ============ Department Detail Modal ============"
if old_detail in content:
    start = content.find(old_detail)
    # Find next section
    end = content.find("\n// Close modals", start)
    if end < 0:
        end = content.find("\ndocument.getElementById", start + 200)
    if start >= 0 and end >= 0:
        new_detail = """// ============ Department Detail Modal (Hierarchical) ============
function showDeptDetail(deptId, deptName, status, color) {
  const deptData = DEPT_AGENTS[deptId];
  const dept = departments.find(d => d.id === deptId) || {};
  const statusLabels = {working:'\U0001f535 \\u5de5\\u4f5c\\u4e2d', thinking:'\U0001f7e1 \\u601d\\u8003\\u4e2d', waiting:'\\u26aa \\u5f85\\u547d', done:'\\u2705 \\u5b8c\\u6210'};
  const st = status || 'waiting';
  const head = deptData?.head;
  const teams = deptData?.teams || [];
  const totalAgents = countAgents(deptData);

  let html = `<div class="dept-detail-header">
    <span class="dept-icon" style="color:${color}">${head?.emoji || '\U0001f4c1'}</span>
    <div>
      <h2>${escHtml(deptName)}</h2>
      <div class="dept-meta">
        <span class="status-dot status-${st}"></span> ${statusLabels[st] || st}
        ${dept.task ? ` \\u00b7 \\u5f53\\u524d\\u4efb\\u52a1: ${escHtml(dept.task)}` : ''}
        ${dept.done ? ` \\u00b7 \\u5b8c\\u6210 ${dept.done} \\u9879` : ''}
        \\u00b7 \U0001f465 ${totalAgents}\\u4eba
      </div>
    </div>
  </div>`;

  if (head) {
    html += `<h4 style="color:var(--gold);margin-bottom:6px;">\U0001f451 \\u90e8\\u957f</h4>
    <div style="display:flex;align-items:center;gap:10px;padding:8px 14px;background:rgba(240,185,11,0.05);border:1px solid var(--gold);border-radius:8px;margin-bottom:10px;">
      <span style="font-size:1.8em;">${head.emoji}</span>
      <div>
        <div style="font-weight:600;">${escHtml(head.name)}</div>
        <div style="font-size:0.78em;color:var(--muted);">${escHtml(head.role)}</div>
        <div style="font-size:0.7em;color:var(--accent);">${escHtml(head.skill)}</div>
      </div>
      <span style="margin-left:auto;font-size:0.7em;">${statusIcon(head.status)}</span>
    </div>`;
  }

  if (teams.length > 0) {
    html += `<h4 style="color:var(--muted);margin-bottom:6px;">\U0001f465 \\u5c0f\\u7ec4\\u53ca\\u6210\\u5458 (${teams.length} \\u7ec4, ${totalAgents-1} \\u4eba)</h4>`;
    teams.forEach(t => {
      html += `<div style="margin-bottom:10px;padding:10px;background:rgba(59,130,246,0.04);border:1px solid var(--border);border-radius:8px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <span style="font-size:1.3em;">${t.lead.emoji||'\U0001f465'}</span>
          <div>
            <div style="font-weight:600;font-size:0.85em;">${escHtml(t.lead.name)} \\u2014 <span style="color:var(--accent);font-size:0.9em;">\\u7ec4\\u957f</span></div>
            <div style="font-size:0.7em;color:var(--muted);">${escHtml(t.lead.role)} \\u00b7 ${escHtml(t.lead.skill)}</div>
          </div>
          <span style="margin-left:auto;font-size:0.7em;">${statusIcon(t.lead.status)}</span>
        </div>`;
      if (t.members && t.members.length > 0) {
        html += '<div style="margin-left:20px;padding-left:12px;border-left:2px solid var(--border);">';
        t.members.forEach(m => {
          html += `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;">
            <span style="font-size:1.1em;">${m.emoji||'\U0001f465'}</span>
            <div style="flex:1;">
              <span style="font-weight:600;font-size:0.8em;">${escHtml(m.name)}</span>
              <span style="font-size:0.68em;color:var(--muted);margin-left:4px;">${escHtml(m.role)}</span>
            </div>
            <span style="font-size:0.65em;">${statusIcon(m.status)}</span>
          </div>`;
        });
        html += '</div>';
      }
      html += '</div>';
    });
  } else {
    html += '<div class="empty-hint">\\u8be5\\u90e8\\u95e8\\u6682\\u65e0\\u5c0f\\u7ec4\\u7ed3\\u6784\\uff0c\\u6309\\u9700\\u5206\\u914d\\u5b50Agent</div>';
  }

  document.getElementById('deptModalContent').innerHTML = html;
  document.getElementById('deptModal').classList.add('active');
}

"""
        content = content[:start] + new_detail + content[end:]
        changes += 1
        print("5. showDeptDetail replaced")
else:
    print("5. showDeptDetail marker not found")

# ======= 6. Update arch modal close + add wheel zoom =======
old_close = "document.getElementById('archModal').addEventListener('click', function(e) {\n  if (e.target === this) this.classList.remove('active');\n});"
new_close = "document.getElementById('archModal').addEventListener('click', function(e) {\n  if (e.target === this) closeArchitecture();\n});\n// Ctrl+wheel zoom on mermaid\nsetTimeout(() => {\n  const ms = document.getElementById('mermaidScroll');\n  if (ms) ms.addEventListener('wheel', function(e) {\n    if (e.ctrlKey || e.metaKey) {\n      e.preventDefault();\n      zoomMermaid(e.deltaY < 0 ? 0.1 : -0.1);\n    }\n  }, {passive: false});\n}, 200);"

if old_close in content:
    content = content.replace(old_close, new_close)
    changes += 1
    print("6. Arch close/wheel replaced")
else:
    print("6. Arch close NOT FOUND, trying alternative")
    # Try to find just the right piece
    start = content.find("archModal').addEventListener('click'")
    if start >= 0:
        line_end = content.find("\n", start)
        # Find the closing of that statement
        line = content[start : line_end + 50]
        print(f"   Found: {repr(line[:120])}")

# ======= 7. Update init log message =======
old_init = (
    "addLog('\U0001f3e6 Chairman Dashboard 初始化完成 (双向通信 v3.0 · 自动批准ON)');"
)
new_init = "addLog('\U0001f3e6 Chairman Dashboard v4.0 初始化完成 (Teams组织架构 · 可缩放架构图 · 自动批准ON)');"
if old_init in content:
    content = content.replace(old_init, new_init)
    changes += 1
    print("7. Init log updated")
else:
    print("7. Init log NOT FOUND")

# ======= 8. Update milestone seed =======
old_milestone = (
    "addMilestone('\U0001f680','Dashboard v3.0 启动 ','自动批准 · 部门架构 · 里程碑');"
)
new_milestone = "addMilestone('\U0001f680','Dashboard v4.0 启动 ','Teams组织架构 · 紧凑网格 · 可缩放架构图');"
if old_milestone in content:
    content = content.replace(old_milestone, new_milestone)
    changes += 1
    print("8. Milestone updated")
else:
    print("8. Milestone NOT FOUND")

with open("company/chairman_dashboard.html", "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n=== Done: {changes} changes applied ===")
