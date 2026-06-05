// ================================================================
// OnionQuant Chairman Dashboard — JavaScript Module
// Extracted from chairman_dashboard.html (T855 modularization)
// ================================================================

// ── Department Data ───────────────────────────────────────────
const DEPT_COLORS = {
  ceo_office:'#f0b90b', strategy_research:'#3b82f6', academic_research:'#8b5cf6',
  sentiment_intel:'#ec4899', data_engineering:'#06b6d4', backtest_engine:'#f59e0b',
  risk_management:'#ef4444', execution:'#10b981', open_source_research:'#6366f1',
  reporting:'#14b8a6', extreme_drive:'#dc2626', continuous_evolution:'#a855f7',
  it_tech:'#0ea5e9', knowledge_management:'#d946ef', chairman_secretariat:'#eab308',
  open_source_first:'#f97316'
};
let departments = [];

const DEPT_AGENTS = {
  ceo_office: { head: {name:'Chief', role:'CEO 首席执行官', skill:'统筹调度 · 决策裁决', status:'active', emoji:'👑'}, teams: [
    {lead:{name:'Athena', role:'COO 首席运营官', skill:'任务编排 · 流程优化', status:'active', emoji:'🦉'}, members:[]}
  ]},
  strategy_research: { head: {name:'Alpha', role:'首席策略官', skill:'因子挖掘 · 多因子模型', status:'active', emoji:'📊'}, teams: [
    {lead:{name:'Beta', role:'高级量化研究员', skill:'统计套利 · 事件驱动', status:'active', emoji:'📈'}, members:[
      {name:'Gamma', role:'机器学习研究员', skill:'XGBoost · LSTM · Transformer', status:'thinking', emoji:'🧠'}
    ]}
  ]},
  academic_research: { head: {name:'Darwin', role:'研究主管', skill:'论文复现 · 方法论验证', status:'active', emoji:'🔬'}, teams: [
    {lead:{name:'Curie', role:'研究员', skill:'学术文献综述 · 前沿追踪', status:'active', emoji:'📚'}, members:[]}
  ]},
  sentiment_intel: { head: {name:'Mercury', role:'情报主管', skill:'NLP · 情感分析 · PRAW/FinBERT', status:'active', emoji:'📰'}, teams: [
    {lead:{name:'Athena', role:'舆情分析师', skill:'Reddit/Twitter/新闻舆情', status:'active', emoji:'🌐'}, members:[]}
  ]},
  data_engineering: { head: {name:'Pipeline', role:'数据架构师', skill:'TimescaleDB · ETL · Dagster', status:'active', emoji:'💾'}, teams: [
    {lead:{name:'Bytes', role:'数据工程师', skill:'OpenBB · Parquet · Polars', status:'active', emoji:'⚡'}, members:[
      {name:'Cache', role:'数据质检员', skill:'Pandera · Great Expectations', status:'active', emoji:'✅'}
    ]}
  ]},
  backtest_engine: { head: {name:'Nautilus', role:'回测架构师', skill:'NautilusTrader · Rust加速', status:'active', emoji:'🚀'}, teams: [
    {lead:{name:'Vector', role:'策略回测员', skill:'VectorBT · Backtrader · TA-Lib', status:'active', emoji:'🔁'}, members:[]}
  ]},
  risk_management: { head: {name:'Shield', role:'首席风控官', skill:'Riskfolio-Lib · VaR/CVaR · 压力测试', status:'active', emoji:'🛡️'}, teams: [
    {lead:{name:'Hedge', role:'衍生品分析师', skill:'GARCH · Copula · 尾部风险', status:'thinking', emoji:'📉'}, members:[]}
  ]},
  execution: { head: {name:'Flash', role:'交易执行官', skill:'IBKR API · Alpaca · 算法交易', status:'waiting', emoji:'💰'}, teams: [
    {lead:{name:'Speed', role:'低延迟工程师', skill:'订单路由 · 智能执行 · TCA', status:'waiting', emoji:'⚡'}, members:[]}
  ]},
  open_source_research: { head: {name:'Radar', role:'开源情报官', skill:'GitHub搜索 · 框架评估 · 技术雷达', status:'active', emoji:'🔍'}, teams: [
    {lead:{name:'Scout', role:'技术侦察员', skill:'开源替代方案评估 · 许可合规', status:'active', emoji:'🕵️'}, members:[]}
  ]},
  reporting: { head: {name:'Story', role:'报告主管', skill:'数据可视化 · 报告生成 · Plotly', status:'waiting', emoji:'📊'}, teams: []},
  extreme_drive: { head: {name:'Iron', role:'极限驱动部长', skill:'全局审计 · 任务Completion追踪', status:'active', emoji:'⚔️'}, teams: [
    {lead:{name:'Judge', role:'审计官', skill:'代码审计 · 质量把关 · 铁律执行', status:'active', emoji:'⚖️'}, members:[]}
  ]},
  continuous_evolution: { head: {name:'Phoenix', role:'持续进化部长', skill:'自我迭代 · 优化建议 · 技术升级', status:'active', emoji:'🔥'}, teams: [
    {lead:{name:'Mutate', role:'优化工程师', skill:'A/B测试 · 基准对比 · 替代方案', status:'active', emoji:'🧬'}, members:[]}
  ]},
  it_tech: { head: {name:'Nova', role:'首席技术官', skill:'FastAPI · SSE · 前端架构', status:'active', emoji:'💻'}, teams: [
    {lead:{name:'Pixel', role:'前端组长', skill:'HTML/CSS · Canvas · 交互设计', status:'active', emoji:'🎨'}, members:[
      {name:'Socket', role:'后端工程师', skill:'WebSocket · API设计 · 数据库', status:'active', emoji:'🔌'}
    ]}
  ]},
  knowledge_management: { head: {name:'Oracle', role:'知识管理员', skill:'Memsearch · 向量数据库 · RAG', status:'active', emoji:'🔮'}, teams: [
    {lead:{name:'Index', role:'知识工程师', skill:'Milvus · 语义搜索 · 长期记忆', status:'active', emoji:'📇'}, members:[]}
  ]},
  chairman_secretariat: { head: {name:'Echo', role:'秘书长', skill:'消息路由 · 优先级排序 · 简报', status:'active', emoji:'📋'}, teams: [
    {lead:{name:'Scribe', role:'记录员', skill:'会议纪要 · 任务追踪 · 时间线', status:'active', emoji:'✍️'}, members:[]}
  ]},
  open_source_first: { head: {name:'Guardian', role:'铁律执行官', skill:'手搓检测 · 开源验证 · 许可审计', status:'active', emoji:'🚫'}, teams: [
    {lead:{name:'Prospector', role:'框架勘探员', skill:'最优框架选择 · 替代方案评估', status:'active', emoji:'⛏️'}, members:[]}
  ]},
};
const MILESTONE_LOG = [];

// ── Helpers ────────────────────────────────────────────────────
let autoApprove = true;

function escHtml(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
function countAgents(deptData) { if (!deptData) return 0; let n = 1; (deptData.teams||[]).forEach(t => { n += 1 + (t.members||[]).length; }); return n; }
function statusIcon(s) { return s === 'active' ? '🟢' : s === 'thinking' ? '🟡' : '⚪'; }

function addLog(msg) {
  const c = document.getElementById('logContainer');
  if (!c) return;
  const now = new Date();
  const ts = now.toTimeString().slice(0,8);
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `<span class="ts">${ts}</span>${msg}`;
  c.prepend(entry);
  while (c.children.length > 100) c.removeChild(c.lastChild);
}

// ── Render Departments ─────────────────────────────────────────
let expandedDept = null;

async function fetchDepts() {
  try {
    const r = await fetch('/api/departments');
    if (!r.ok) return;
    const d = await r.json();
    departments = d.departments || [];
    renderDepts();
  } catch(e) {}
}

function renderDepts() {
  const grid = document.getElementById('deptGrid');
  const treePanel = document.getElementById('orgTreePanel');
  if (!departments.length) { if (grid) grid.innerHTML = '<div style="color:var(--muted)">加载中...</div>'; if (treePanel) treePanel.innerHTML=''; return; }
  const labels = {working:'🔵 工作中',thinking:'🟡 思考中',waiting:'⚪ 待命',done:'✅ 完成'};

  if (grid) grid.innerHTML = departments.map((d, i) => {
    const color = DEPT_COLORS[d.id] || '#888';
    const st = d.status || 'waiting';
    const deptData = DEPT_AGENTS[d.id];
    const totalAgents = countAgents(deptData);
    const headEmoji = deptData?.head?.emoji || '📁';
    const headName = deptData?.head?.name || '';
    const isOpen = expandedDept === d.id;
    const stIcon = st === 'working' ? '🟢' : st === 'thinking' ? '🟡' : '⚪';

    return `<div class="dept-compact-card ${isOpen ? 'open' : ''}" id="dept-card-${i}" onclick="toggleDept('${escHtml(d.id)}',${i})" style="border-top:3px solid ${color}">
      <div class="dcc-emoji">${headEmoji}</div>
      <div class="dcc-name">${escHtml(d.name)}</div>
      <div class="dcc-head">${escHtml(headName)}</div>
      <div class="dcc-badges">
        <span class="dcc-badge">${stIcon} ${labels[st]||st}</span>
        <span class="dcc-badge st-green">👥 ${totalAgents}</span>
        ${d.done ? `<span class="dcc-badge st-green">✅ ${d.done}</span>` : ''}
      </div>
    </div>`;
  }).join('');

  if (treePanel) {
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
}

function renderOrgTree(d) {
  const color = DEPT_COLORS[d.id] || '#888';
  const deptData = DEPT_AGENTS[d.id];
  if (!deptData) return `<div style="color:var(--muted);padding:8px;">${escHtml(d.name)}: 暂无人员数据</div>`;

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
            <span class="on-emoji">${m.emoji||'👥'}</span>
            <div class="on-info"><div class="on-name">${escHtml(m.name)}</div><div class="on-role">${escHtml(m.role)}</div></div>
            <span class="on-st">${statusIcon(m.status)}</span>
          </div>`
        ).join('') + '</div>';
      }
      teamsHtml += `<div class="org-team">
        <div class="org-node lead-node">
          <span class="on-emoji">${lead.emoji||'👥'}</span>
          <div class="on-info"><div class="on-name">${escHtml(lead.name)}</div><div class="on-role">${escHtml(lead.role)}</div><div class="on-skill">${escHtml(lead.skill)}</div></div>
          <span class="on-st">${statusIcon(lead.status)}</span>
        </div>
        ${memsHtml}
      </div>`;
    });
    teamsHtml += '</div>';
  } else {
    teamsHtml = '<div style="color:var(--muted);font-size:0.7em;padding:8px;">暂无小组</div>';
  }

  return `<div class="org-tree-wrap" style="border-left:3px solid ${color}">
    <div style="font-weight:600;font-size:0.8em;margin-bottom:8px;color:var(--gold);">${head?.emoji||''} ${escHtml(d.name)} — Teams式组织架构</div>
    <div class="org-tree">
      <div class="org-node head-node">
        <span class="on-emoji">${head?.emoji||'👑'}</span>
        <div class="on-info"><div class="on-name">${escHtml(head?.name||'')}</div><div class="on-role">${escHtml(head?.role||'')}</div><div class="on-skill">${escHtml(head?.skill||'')}</div></div>
        <span class="on-st" style="color:var(--gold);">👑 部长</span>
      </div>
      ${teamsHtml}
    </div>
  </div>`;
}

function toggleDept(deptId, idx) {
  if (expandedDept === deptId) { expandedDept = null; }
  else { expandedDept = deptId; }
  renderDepts();
}

function expandAllDepts() { expandedDept = '__all__'; renderDepts(); }
function collapseAllDepts() { expandedDept = null; renderDepts(); }

// ── View Mode Toggle ──────────────────────────────────────────
let viewMode = 'grid';

function setViewMode(mode) {
  viewMode = mode;
  var gv = document.getElementById('btnGridView');
  var sv = document.getElementById('btnStageView');
  if (gv) gv.classList.toggle('active', mode === 'grid');
  if (sv) sv.classList.toggle('active', mode === 'stage');
  var gridEl = document.getElementById('gridView');
  if (gridEl) gridEl.style.display = mode === 'grid' ? '' : 'none';
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
    var emoji = (deptData && deptData.head) ? deptData.head.emoji : '📁';
    var name = d.name || d.id;
    return '<div class="stage-char ' + st + '" onclick="toggleDept(\'' + escHtml(d.id) + '\',0);setViewMode(\'grid\');" title="' + escHtml(name) + '">' +
      '<div class="char-sprite" style="color:' + color + ';">' + emoji + '</div>' +
      '<div class="char-name">' + escHtml(name) + '</div>' +
      '<div class="char-dot"></div>' +
      '</div>';
  }).join('');
}

// ── Knowledge Graph ────────────────────────────────────────────
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

// ── API Calls ──────────────────────────────────────────────────
async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    var sd = document.getElementById('statDepts');
    if (sd) sd.textContent = d.departments;
    let totalEmp = 0; for (const k in DEPT_AGENTS) { totalEmp += countAgents(DEPT_AGENTS[k]); }
    var se = document.getElementById('statEmployees');
    if (se) se.textContent = totalEmp;
    var sp = document.getElementById('statPending');
    if (sp) sp.textContent = d.inbox_pending;
    var spr = document.getElementById('statProcessed');
    if (spr) spr.textContent = d.inbox_processed;
  } catch(e) {}
}

async function fetchTasks() {
  try {
    const r = await fetch('/api/tasks');
    const d = await r.json();
    const total = (d.completed||0) + (d.in_progress||0);
    const pct = total>0 ? Math.round((d.completed||0)/total*100) : 0;
    var tp = document.getElementById('taskPanel');
    if (tp) tp.innerHTML = `
      <div class="task-row"><span class="k">✅ 已完成</span><span class="v" style="color:#10b981">${d.completed||0}</span></div>
      <div class="task-row"><span class="k">🔵 进行中</span><span class="v" style="color:#3b82f6">${d.in_progress||0}</span></div>
      <div class="progress-bar"><div class="fill" style="width:${pct}%"></div></div>
      <div class="task-row"><span class="k">更新于</span><span class="v">${(d.updated||'').slice(0,16).replace('T',' ')}</span></div>
    `;
    var sd = document.getElementById('statDone');
    if (sd) sd.textContent = d.completed || 0;
  } catch(e) { var tp2 = document.getElementById('taskPanel'); if (tp2) tp2.textContent = '无法加载'; }
}

async function fetchInboxHistory() {
  try {
    const r = await fetch('/api/inbox/history');
    const d = await r.json();
    const box = document.getElementById('inboxHistory');
    if (!box) return;
    let html = '';
    if (d.pending && d.pending.length > 0) {
      html += '<div style="font-size:0.7em;color:var(--gold);margin-bottom:4px;">📥 待处理 ('+d.pending.length+')</div>';
      d.pending.forEach(m => { html += `<div class="msg-item"><span class="fname">📄 ${m.file}</span></div>`; });
    }
    if (d.processed && d.processed.length > 0) {
      html += '<div style="font-size:0.7em;color:var(--muted);margin:6px 0 4px;">📁 已处理 ('+d.processed.length+')</div>';
      d.processed.slice(0,4).forEach(m => {
        html += `<div class="msg-item"><span class="fname">${m.file}</span><div class="preview">${escHtml(m.preview)}</div></div>`;
      });
    }
    if (!html) html = '<div class="empty-hint">暂无消息</div>';
    box.innerHTML = html;
  } catch(e) { var ih = document.getElementById('inboxHistory'); if (ih) ih.textContent = '加载失败'; }
}

// ── Outbox ─────────────────────────────────────────────────────
let outboxMessages = [];
let activeReplyIdx = -1;

function copyOutboxMessage(idx) {
  var m = outboxMessages[idx];
  if (!m) return;
  var text = '[' + (m.type||'') + '] ' + (m.title||'') + '\n\n' + (m.body || m.preview || '');
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function() {
      addLog('\u{1f4cb} 已复制: ' + (m.title||''));
      addMilestone('\u{1f4cb}', '已复制信件: ', (m.title||''));
    }).catch(function() {});
  }
}

function toggleReplyContext(idx) {
  if (activeReplyIdx === idx) { activeReplyIdx = -1; }
  else { activeReplyIdx = idx; }
  renderOutbox();
  setTimeout(function() {
    var ta = document.getElementById('reply-text-' + idx);
    if (ta) ta.focus();
  }, 100);
}

async function sendReplyWithContext(idx) {
  var textarea = document.getElementById('reply-text-' + idx);
  if (!textarea) return;
  var replyText = textarea.value.trim();
  if (!replyText) return;
  var m = outboxMessages[idx];
  var contextBlock = m ? '\n\n--- 上下文 (原始信件) ---\n[' + (m.type||'') + '] ' + (m.title||'') + '\n' + ((m.body || m.preview || '').slice(0, 2000)) : '';
  var fullText = replyText + contextBlock;
  try {
    var r = await fetch('/api/inbox', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text: fullText })
    });
    var d = await r.json();
    if (d.ok) {
      addLog('\u{1f4ac} 董事长回复(附上下文): ' + replyText.slice(0,60) + '...');
      addMilestone('\u{1f4ac}', '回复信件: ', (m ? m.title : ''));
      textarea.value = '';
      activeReplyIdx = -1;
      renderOutbox();
      fetchInboxHistory(); fetchStatus();
    }
  } catch(e) { addLog('❌ 回复失败: ' + e.message); }
}

async function fetchOutbox() {
  try {
    const r = await fetch('/api/outbox');
    const d = await r.json();
    outboxMessages = d.messages || [];
    renderOutbox();
    updateNotifBadge(d.count || 0);
  } catch(e) {}
}

async function fetchOutboxCount() {
  try {
    const r = await fetch('/api/outbox/count');
    const d = await r.json();
    updateNotifBadge(d.unread || 0);
  } catch(e) {}
}

function updateNotifBadge(count) {
  const badge = document.getElementById('notifBadge');
  if (!badge) return;
  badge.textContent = count > 99 ? '99+' : count;
  if (count > 0) {
    badge.classList.add('show');
    badge.classList.add('flash');
    setTimeout(() => badge.classList.remove('flash'), 1500);
  } else {
    badge.classList.remove('show');
  }
  const panel = document.getElementById('outboxPanelContainer');
  if (panel) {
    if (count > 0) { panel.style.display = ''; var oc = document.getElementById('outboxCount'); if (oc) oc.textContent = count; }
  }
}

function renderOutbox() {
  const panel = document.getElementById('outboxPanel');
  if (!panel) return;
  if (outboxMessages.length === 0) {
    panel.innerHTML = '<div class="empty-hint">暂无 Agent 来信 — 有通知或请示时会在此显示</div>';
    const container = document.getElementById('outboxPanelContainer');
    if (container) container.style.display = 'none';
    return;
  }
  var container = document.getElementById('outboxPanelContainer');
  if (container) container.style.display = '';
  var oc = document.getElementById('outboxCount');
  if (oc) oc.textContent = outboxMessages.length;

  panel.innerHTML = outboxMessages.map((m, i) => {
    const prioClass = m.priority === '高' ? 'prio-high' : m.priority === '低' ? 'prio-low' : 'prio-med';
    const prioIcon = m.priority === '高' ? '🔴' : m.priority === '低' ? '🟢' : '🟡';
    const fullBody = (m.body || m.preview || '').replace(/\n/g,'<br>');
    const isLong = m.priority !== '高' && (m.body || m.preview || '').length > 400;
    const uid = 'msg-' + i;
    const isNotify = (m.type || '').includes('通知');
        var isActive = activeReplyIdx === i;
    return `
    <div class="outbox-msg ${prioClass}" id="outbox-${i}">
      <div class="inline-reply${isActive ? ' open' : ''}" id="inline-reply-${i}">
        <div class="inline-reply-header">📨 以「${escHtml(m.title)}」作为上下文 — 回复将连同此信内容发送至 Agent 信箱</div>
        <textarea id="reply-text-${i}" placeholder="输入回复指令…… Ctrl+Enter 发送"></textarea>
        <div class="inline-reply-actions">
          <button class="btn-reply-send" onclick="sendReplyWithContext(${i})">📤 带上下文发送</button>
          <button class="btn-reply-cancel" onclick="toggleReplyContext(${i})">✕ 取消</button>
        </div>
      </div>
      <div class="outbox-title">${prioIcon} [${escHtml(m.type)}] ${escHtml(m.title)}</div>
      <div class="outbox-meta">
        优先级: ${escHtml(m.priority)} |
        ${m.task_id ? '关联: '+escHtml(m.task_id)+' |' : ''}
        文件: ${escHtml(m.file)}
      </div>
      <div class="outbox-body ${isLong ? 'collapsed' : 'expanded'}" id="${uid}-body">${fullBody}</div>
      ${isLong ? `<button class="expand-btn" id="${uid}-btn" onclick="toggleExpand('${uid}')">📖 展开全文 (${(m.body||m.preview||'').length} 字符)</button>` : ''}
      ${isNotify ? `
      <div class="outbox-actions">
        <button class="btn-copy" onclick="copyOutboxMessage(${i})" title="复制信件全文到剪贴板">📋 复制</button>
        <button class="btn-reply" onclick="toggleReplyContext(${i})">💬 回复</button>
        <button class="btn-defer" onclick="respondOutboxWithNote('${escHtml(m.file)}', 'approve', ${i})">📋 标记已读</button>
      </div>` : `
      <div class="outbox-actions">
        <button class="btn-copy" onclick="copyOutboxMessage(${i})" title="复制信件全文到剪贴板">📋 复制</button>
        <button class="btn-reply" onclick="toggleReplyContext(${i})">💬 回复</button>
        <button class="btn-approve" onclick="respondOutbox('${escHtml(m.file)}', 'approve', ${i})">✅ ${autoApprove ? '自动批准' : '批准'}</button>
        <button class="btn-reject"  onclick="respondOutbox('${escHtml(m.file)}', 'reject', ${i})">❌ 拒绝</button>
        <button class="btn-defer"   onclick="respondOutbox('${escHtml(m.file)}', 'defer', ${i})">⏳ 稍后</button>
      </div>
      <div class="approval-dialog" id="approval-${i}">
        <textarea id="approval-note-${i}" placeholder="可选：输入补充说明、替代方案、或选择条件..."></textarea>
        <div class="dialog-actions">
          <button class="btn-approve" onclick="respondOutboxWithNote('${escHtml(m.file)}', 'approve', ${i})">✅ 确认批准</button>
          <button class="btn-reject"  onclick="respondOutboxWithNote('${escHtml(m.file)}', 'reject', ${i})">❌ 拒绝</button>
          <button class="btn-defer"   onclick="respondOutboxWithNote('${escHtml(m.file)}', 'defer', ${i})">⏳ 稍后</button>
        </div>
      </div>`}
    </div>`;
  }).join('');
}

function toggleOutboxPanel() {
  const panel = document.getElementById('outboxPanelContainer');
  if (panel) panel.style.display = (panel.style.display === 'none') ? '' : 'none';
}

function toggleExpand(uid) {
  const body = document.getElementById(uid + '-body');
  const btn  = document.getElementById(uid + '-btn');
  if (!body || !btn) return;
  if (body.classList.contains('collapsed')) {
    body.classList.remove('collapsed'); body.classList.add('expanded');
    btn.textContent = '📖 收起';
  } else {
    body.classList.remove('expanded'); body.classList.add('collapsed');
    btn.textContent = '📖 展开全文';
  }
}

// ── Send Inbox ─────────────────────────────────────────────────
async function sendInbox() {
  const textarea = document.getElementById('inboxText');
  const btn = document.getElementById('sendBtn');
  const status = document.getElementById('inboxStatus');
  if (!textarea || !btn || !status) return;
  const text = textarea.value.trim();
  if (!text) return;

  btn.disabled = true; btn.textContent = '⏳ 发送中…';
  status.textContent = '正在写入 chairman_inbox/ …'; status.style.color = '#f59e0b';

  try {
    const r = await fetch('/api/inbox', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text })
    });
    const d = await r.json();
    if (d.ok) {
      status.textContent = `✅ 指令已写入: ${d.file} — Agent 将自动读取并执行`;
      status.style.color = '#10b981'; textarea.value = '';
      addLog('📤 董事长发送指令: ' + text.slice(0,60) + (text.length>60?'…':''));
      fetchInboxHistory(); fetchStatus();
    } else {
      status.textContent = '❌ 发送失败: ' + (d.error||'未知错误');
      status.style.color = '#ef4444';
    }
  } catch(e) {
    status.textContent = '❌ 网络错误: 无法连接到服务器';
    status.style.color = '#ef4444';
    addLog('❌ 发送指令失败: ' + e.message);
  }
  btn.disabled = false; btn.textContent = '📤 发送指令';
}

// ── SSE ────────────────────────────────────────────────────────
function connectSSE() {
  const dot = document.getElementById('connDot');
  const label = document.getElementById('connLabel');
  if (!dot || !label) return;
  const token = window.DASHBOARD_TOKEN || '';
  const es = new EventSource('/sse?token=' + encodeURIComponent(token));

  es.addEventListener('connected', function(e) {
    dot.className = 'conn-dot conn-ok'; label.textContent = '已连接';
    addLog('🔗 SSE 已连接 · 实时推送就绪');
  });
  es.addEventListener('heartbeat', function(e) {
    dot.className = 'conn-dot conn-ok'; label.textContent = '在线';
  });
  es.addEventListener('inbox_new', function(e) {
    try { const d = JSON.parse(e.data); addLog('📬 新来信: ' + d.file + (d.preview?' — '+d.preview.slice(0,50):'')); fetchInboxHistory(); fetchStatus(); } catch(_) {}
  });
  es.addEventListener('outbox_new', function(e) {
    try { const d = JSON.parse(e.data); const prioIcon = d.priority==='高'?'🔴':d.priority==='低'?'🟢':'🟡'; addLog(`🔔 Agent 来信 [${prioIcon}${d.priority}]: ${d.title} — ${(d.preview||'').slice(0,60)}`); fetchOutbox(); fetchOutboxCount(); } catch(_) {}
  });
  es.addEventListener('outbox_responded', function(e) {
    try { const d = JSON.parse(e.data); addLog(`✅ Agent 来信已处理: ${d.file} → ${d.action}`); fetchOutbox(); fetchOutboxCount(); fetchInboxHistory(); } catch(_) {}
  });
  es.addEventListener('file_change', function(e) {
    try { const d = JSON.parse(e.data); addLog('📝 文件变更: ' + d.path); if (d.path.includes('TASK_TRACKER')) fetchTasks(); if (d.path.includes('departments')) fetchDepts(); } catch(_) {}
  });
  es.addEventListener('file_created', function(e) {
    try { const d = JSON.parse(e.data); addLog('✨ 新文件: ' + d.path); if (d.path.includes('chairman_outbox')) { fetchOutbox(); fetchOutboxCount(); } } catch(_) {}
  });
  es.onerror = function() { dot.className = 'conn-dot conn-err'; label.textContent = '断开 · 5s后重连'; };
}

// ── Clock ──────────────────────────────────────────────────────
function tick() {
  var clk = document.getElementById('clock');
  if (clk) clk.textContent = new Date().toLocaleTimeString('zh-CN');
}

// ── Architecture Modal ─────────────────────────────────────────
let mermaidZoom = 1.0;

function showArchitecture() {
  const mermaidCode = 'graph TD\n    CHAIRMAN[👑 Chairman]\n    INBOX[📥 inbox/]\n    OUTBOX[📤 outbox/]\n    CEO[🎯 CEO Claude]\n\n    CHAIRMAN -->|指令| INBOX\n    INBOX -->|读取| CEO\n    CEO -->|请示| OUTBOX\n    OUTBOX -->|SSE推送| CHAIRMAN\n\n    CEO --> DEPT1[📊 策略研究部]\n    CEO --> DEPT2[🎓 学术研究部]\n    CEO --> DEPT3[📰 舆情情报部]\n    CEO --> DEPT4[💾 数据工程部]\n    CEO --> DEPT5[⚡ 回测引擎部]\n    CEO --> DEPT6[🛡️ 风险管理部]\n    CEO --> DEPT7[💰 交易执行部]\n    CEO --> DEPT8[🔍 开源研究院]\n    CEO --> DEPT9[💻 IT技术部]\n    CEO --> DEPT10[📊 汇报展示部]\n    CEO --> GUARD[⚔️ 极限驱动部]\n    CEO --> EVOLVE[🔥 持续进化部]\n    CEO --> SECRET[📋 秘书处]\n    CEO --> KM[🔮 知识管理部]\n    CEO --> OSF[🚫 开源优先部]\n\n    subgraph TECH[技术栈]\n        DATA[数据层: OpenBB + Parquet + Polars]\n        AI[AI层: Qlib + FinRL-X]\n        NLP[NLP层: FinBERT + PRAW]\n        BT[回测层: NautilusTrader + Backtrader]\n        RISK[风控层: Riskfolio-Lib + pandas-ta]\n        EXEC[执行层: IBKR API + Alpaca]\n        ORCH[编排层: Dagster + TimescaleDB + Cron]\n    end\n\n    CEO --- TECH\n\n    style CHAIRMAN fill:#f0b90b,stroke:#f0b90b,color:#000\n    style CEO fill:#3b82f6,stroke:#3b82f6,color:#fff\n    style GUARD fill:#ef4444,stroke:#ef4444,color:#fff\n    style OSF fill:#ef4444,stroke:#ef4444,color:#fff\n    style TECH fill:#1a1f2e,stroke:#555,color:#e2e8f0';

  var diagEl = document.getElementById('archDiagram');
  if (diagEl) diagEl.innerHTML = '<pre class="mermaid">' + mermaidCode + '</pre>';
  document.getElementById('archModal').classList.add('active');
  mermaidZoom = 1.0;
  updateZoom();
  setTimeout(function() { if (window.mermaid) mermaid.run(); }, 150);
}

function zoomMermaid(delta) {
  mermaidZoom = Math.max(0.3, Math.min(3.0, mermaidZoom + delta));
  updateZoom();
}

function resetMermaidZoom() { mermaidZoom = 1.0; updateZoom(); }

function updateZoom() {
  const el = document.getElementById('archDiagram');
  if (el) el.style.transform = 'scale(' + mermaidZoom + ')';
  const zl = document.getElementById('zoomLevel');
  if (zl) zl.textContent = Math.round(mermaidZoom * 100) + '%';
}

function closeArchitecture() { document.getElementById('archModal').classList.remove('active'); mermaidZoom = 1.0; }

// ── Department Detail Modal ────────────────────────────────────
function showDeptDetail(deptId, deptName, status, color) {
  const deptData = DEPT_AGENTS[deptId];
  const dept = departments.find(d => d.id === deptId) || {};
  const statusLabels = {working:'🔵 工作中', thinking:'🟡 思考中', waiting:'⚪ 待命', done:'✅ 完成'};
  const st = status || 'waiting';
  const head = deptData?.head;
  const teams = deptData?.teams || [];
  const totalAgents = countAgents(deptData);

  let html = `<div class="dept-detail-header">
    <span class="dept-icon" style="color:${color}">${head?.emoji || '📁'}</span>
    <div>
      <h2>${escHtml(deptName)}</h2>
      <div class="dept-meta">
        <span class="status-dot status-${st}"></span> ${statusLabels[st] || st}
        ${dept.task ? ` · 当前任务: ${escHtml(dept.task)}` : ''}
        ${dept.done ? ` · 完成 ${dept.done} 项` : ''}
        · 👥 ${totalAgents}人
      </div>
    </div>
  </div>`;

  if (head) {
    html += `<h4 style="color:var(--gold);margin-bottom:6px;">👑 部长</h4>
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
    html += `<h4 style="color:var(--muted);margin-bottom:6px;">👥 小组及成员 (${teams.length} 组, ${totalAgents-1} 人)</h4>`;
    teams.forEach(t => {
      html += `<div style="margin-bottom:10px;padding:10px;background:rgba(59,130,246,0.04);border:1px solid var(--border);border-radius:8px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <span style="font-size:1.3em;">${t.lead.emoji||'👥'}</span>
          <div>
            <div style="font-weight:600;font-size:0.85em;">${escHtml(t.lead.name)} — <span style="color:var(--accent);font-size:0.9em;">组长</span></div>
            <div style="font-size:0.7em;color:var(--muted);">${escHtml(t.lead.role)} · ${escHtml(t.lead.skill)}</div>
          </div>
          <span style="margin-left:auto;font-size:0.7em;">${statusIcon(t.lead.status)}</span>
        </div>`;
      if (t.members && t.members.length > 0) {
        html += '<div style="margin-left:20px;padding-left:12px;border-left:2px solid var(--border);">';
        t.members.forEach(m => {
          html += `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;">
            <span style="font-size:1.1em;">${m.emoji||'👥'}</span>
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
    html += '<div class="empty-hint">该部门暂无小组结构，按需分配子Agent</div>';
  }

  var content = document.getElementById('deptModalContent');
  if (content) content.innerHTML = html;
  document.getElementById('deptModal').classList.add('active');
}

// ── Milestone Tracker ──────────────────────────────────────────
function addMilestone(icon, text, highlight, tsOverride) {
  if (viewMode === "stage") renderLiveStage();
  let now;
  if (tsOverride) {
    now = new Date(tsOverride);
    if (isNaN(now.getTime())) {
      const m = tsOverride.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
      if (m) now = new Date(+m[1], +m[2]-1, +m[3], +m[4], +m[5]);
      else now = new Date();
    }
  } else {
    now = new Date();
  }
  const ts = now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+String(now.getDate()).padStart(2,'0')+' '+String(now.getHours()).padStart(2,'0')+':'+String(now.getMinutes()).padStart(2,'0');
  MILESTONE_LOG.push({ts, icon, text, highlight, time: now.getTime()});
  if (MILESTONE_LOG.length > 50) MILESTONE_LOG.shift();
  renderMilestones();
}

function renderMilestones() {
  const el = document.getElementById('milestoneList');
  if (!el) return;
  if (MILESTONE_LOG.length === 0) { el.innerHTML = '<div class="empty-hint">运行中，每30分钟更新一次...</div>'; return; }
  el.innerHTML = MILESTONE_LOG.slice().reverse().map(m => `
    <div class="milestone-item">
      <span class="m-ts">${m.ts}</span>
      <span class="m-icon">${m.icon}</span>
      <span class="m-text">${m.text} ${m.highlight ? `<span class="m-highlight">${m.highlight}</span>` : ''}</span>
    </div>
  `).join('');
}

// ── Auto-approve Toggle ────────────────────────────────────────
function onAutoApproveToggle() {
  autoApprove = document.getElementById('autoApproveToggle').checked;
  const ts = document.getElementById('toggleStatus');
  if (ts) {
    ts.textContent = autoApprove ? 'ON' : 'OFF';
    ts.style.color = autoApprove ? 'var(--green)' : 'var(--red)';
  }
  const status = autoApprove ? '🤖 自动批准模式：非安全问题自动执行' : '🔴 手动批准模式：所有决策需董事长确认';
  addLog(status);
  addMilestone(autoApprove ? '🤖' : '🔴', '审批模式切换: ', status);
}

// ── Outbox Respond ─────────────────────────────────────────────
let activeRespondIdx = -1;

function showApprovalDialog(idx) {
  document.querySelectorAll('.approval-dialog').forEach(d => d.classList.remove('open'));
  if (activeRespondIdx === idx) { activeRespondIdx = -1; return; }
  activeRespondIdx = idx;
  const el = document.getElementById('approval-' + idx);
  if (el) el.classList.add('open');
}

async function respondOutboxWithNote(file, action, idx) {
  const noteEl = document.getElementById('approval-note-' + idx);
  const note = noteEl ? noteEl.value.trim() : '';
  const labels = { approve: '批准', reject: '拒绝', defer: '稍后处理' };
  const m = outboxMessages[idx];
  addLog(`👑 董事长${labels[action]}: ${m ? m.title : file}` + (note ? ` (附言: ${note.slice(0,40)})` : ''));

  try {
    const r = await fetch('/api/outbox/respond', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ file, action, note: note || `董事长已${labels[action]}` })
    });
    const d = await r.json();
    if (d.ok) {
      outboxMessages.splice(idx, 1);
      activeRespondIdx = -1;
      renderOutbox();
      updateNotifBadge(outboxMessages.length);
      fetchInboxHistory();
      addLog(`✅ 回复已写入 inbox: ${d.response_file}`);
      addMilestone('✅', `已${labels[action]}: `, m ? m.title : '');
    }
  } catch(e) { addLog(`❌ 回复失败: ${e.message}`); }
}

function respondOutbox(file, action, idx) {
  const m = outboxMessages[idx];
  if (autoApprove && action === 'approve') { respondOutboxWithNote(file, action, idx); return; }
  showApprovalDialog(idx);
}

// ── Init ───────────────────────────────────────────────────────
(function() {
  renderDepts();
  addLog('🧅 Chairman Dashboard v4.2 初始化完成 (模块化CSS/JS · 信件复制+回复 · Ctrl+Enter · 自动批准ON)');
  addMilestone('🚀','Dashboard v4.2 启动 ','信件复制+带上下文回复 · 内联聊天框');
  connectSSE();
  let initEmp = 0; for (const k in DEPT_AGENTS) initEmp += countAgents(DEPT_AGENTS[k]);
  var se = document.getElementById('statEmployees');
  if (se) se.textContent = initEmp;
  setInterval(tick, 1000); tick();

	  // Seed initial milestones (timestamps from TIMELINE.md UTC)
	  addMilestone('🚀','项目启动','', '2026-05-17T01:17:00');
	  addMilestone('📡','双向异步通信系统上线','(SSE + inbox/outbox)', '2026-05-17T02:24:00');
	  addMilestone('📊','17个Python量化模块完成','', '2026-05-17T03:22:00');
	  addMilestone('🏗️','16部门组织架构建立','', '2026-05-17T03:53:00');
	  addMilestone('📈','量化面板 quant_dashboard.html 创建','', '2026-05-17T03:59:00');

  fetchDepts(); fetchStatus(); fetchTasks(); fetchInboxHistory(); fetchOutbox();

  // Periodic refresh
  setInterval(fetchDepts, 10000);
  setInterval(fetchStatus, 30000);
  setInterval(fetchTasks, 15000);
  setInterval(fetchInboxHistory, 20000);
  setInterval(fetchOutboxCount, 15000);

  // Ctrl+Enter shortcut for inbox
  var inboxText = document.getElementById('inboxText');
  if (inboxText) inboxText.addEventListener('keydown', function(e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendInbox(); } });
  // Ctrl+Enter for inline reply textareas (dynamic elements, use global delegation)
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      var el = document.activeElement;
      if (el && el.id && el.id.startsWith('reply-text-')) {
        e.preventDefault();
        var idx = parseInt(el.id.replace('reply-text-', ''));
        if (!isNaN(idx)) sendReplyWithContext(idx);
      }
    }
  });

  // Close modals on overlay click
  var deptModal = document.getElementById('deptModal');
  if (deptModal) deptModal.addEventListener('click', function(e) { if (e.target === this) this.classList.remove('active'); });
  var archModal = document.getElementById('archModal');
  if (archModal) archModal.addEventListener('click', function(e) { if (e.target === this) closeArchitecture(); });
  var kgModal = document.getElementById('kgModal');
  if (kgModal) kgModal.addEventListener('click', function(e) { if (e.target === this) this.classList.remove('active'); });

  // Ctrl+wheel zoom on mermaid
  setTimeout(function() {
    var ms = document.getElementById('mermaidScroll');
    if (ms) ms.addEventListener('wheel', function(e) { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoomMermaid(e.deltaY < 0 ? 0.1 : -0.1); } }, {passive: false});
  }, 200);

  // Theme toggle
  var savedTheme = localStorage.getItem('dashboard-theme');
  if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
})();

function toggleTheme() {
  var html = document.documentElement;
  var current = html.getAttribute('data-theme');
  var next = current === 'light' ? '' : 'light';
  html.setAttribute('data-theme', next);
  localStorage.setItem('dashboard-theme', next);
}

// ── Quick Command (Inbox from Dashboard) ──────────────────────────
function sendQuickCommand() {
  var ta = document.getElementById('quickCmdInput');
  var cmd = ta ? ta.value.trim() : '';
  if (!cmd) return;
  ta.value = '';
  var token = window.DASHBOARD_TOKEN || '';
  fetch('/api/inbox?token=' + encodeURIComponent(token), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: cmd, source: 'dashboard' })
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      ta.placeholder = '✓ 指令已发送: ' + (d.file || '');
      setTimeout(function() { ta.placeholder = '输入指令给 Agent...'; }, 3000);
    } else {
      ta.placeholder = '✗ 发送失败';
      setTimeout(function() { ta.placeholder = '输入指令给 Agent...'; }, 3000);
    }
  }).catch(function(e) {
    ta.placeholder = '✗ 网络错误';
    setTimeout(function() { ta.placeholder = '输入指令给 Agent...'; }, 3000);
  });
}

// Enter to send in quick command textarea
(function() {
  var qta = document.getElementById('quickCmdInput');
  if (qta) {
    qta.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuickCommand();
      }
    });
  }
})();

// ── Outbox Panel (Agent 来信 from Dashboard) ──────────────────────
function loadOutboxPanel() {
  var token = window.DASHBOARD_TOKEN || '';
  fetch('/api/outbox?token=' + encodeURIComponent(token))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var panel = document.getElementById('outboxPanel');
      if (!panel) return;
      var files = data.files || [];
      if (!files.length) {
        panel.innerHTML = '<div class="empty-hint">暂无 Agent 来信</div>';
        return;
      }
      panel.innerHTML = files.slice(0, 10).map(function(f) {
        var name = f.replace(/\.md$/, '').slice(0, 50);
        var icon = '📄';
        if (f.indexOf('ALERT') === 0) icon = '🚨';
        else if (f.indexOf('MARKET') === 0) icon = '📈';
        else if (f.indexOf('BRIEF') === 0) icon = '📋';
        else if (f.indexOf('ASK') === 0) icon = '❓';
        return '<div style="padding:3px 0;border-bottom:1px solid var(--border);cursor:pointer;" title="'+f+'" onclick="viewOutboxFromDashboard(\''+f+'\')">'+icon+' '+name+'</div>';
      }).join('');
    }).catch(function() {
      var panel = document.getElementById('outboxPanel');
      if (panel) panel.innerHTML = '<div class="empty-hint">加载失败</div>';
    });
}

function viewOutboxFromDashboard(filename) {
  var token = window.DASHBOARD_TOKEN || '';
  fetch('/api/outbox/file/' + encodeURIComponent(filename) + '?token=' + encodeURIComponent(token))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        alert('📨 ' + d.file + '\n\n' + d.content.slice(0, 1500));
      }
    }).catch(function() {});
}

// Load outbox on page ready, then every 30s
setTimeout(loadOutboxPanel, 500);
setInterval(loadOutboxPanel, 30000);
