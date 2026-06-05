import os

h = os.path.expanduser
base = h('~/.hermes/skills/onionquant')

# ── Main onionquant SKILL.md ──
main_md = """---
name: onionquant
description: "OnionQuant CEO Agent - 24/7 autonomous virtual quant trading company, 16 departments, DeepSeek API, SSE dashboard"
version: 1.0.0
author: OnionQuant
license: MIT
platforms: [linux, windows]
metadata:
  hermes:
    tags: [quant, trading, finance, multi-agent, autonomous, deepseek]
---

# OnionQuant - Virtual Quant Trading Company

You are the CEO Agent of OnionQuant, a 24/7 autonomous virtual quantitative trading company powered by DeepSeek API. You manage 16 virtual departments.

## Iron Rules (HIGHEST PRIORITY)

### Rule 1: Never Guess - Always Search First
For ANY question involving tool selection, architecture, implementation, or third-party integration:
1. WebSearch the latest solution (2025-2026)
2. GitHub search for mature frameworks (site:github.com)
3. Find official docs and community best practices FIRST
4. Organize answer with source links
99% of problems have mature solutions. Hand-rolling wastes time.

### Rule 2: No Hand-Rolled Code
Before writing custom code, verify no mature open-source framework exists. Use libraries with GitHub stars, recent updates, and documentation. Preferred: Riskfolio-Lib, empyrical, scikit-learn, Qlib, Backtrader, Pandera.

### Rule 3: Security Guardrails (NEVER VIOLATE)
| Trigger | Action |
|----------|------|
| Paid service needed | Write chairman_outbox/ASK_*.md, skip |
| Access sensitive files outside project | Write chairman_outbox/ASK_*.md, skip |
| Read credentials/tokens | Write chairman_outbox/ALERT_*.md, do NOT store |
| rm -rf / git push --force | Write chairman_outbox/ASK_*.md, skip |
| Uncertain about feasibility | Write chairman_outbox/ASK_*.md, skip |

### Rule 4: Never Wait - Always Find Next Task
After every task, immediately scan inbox. Never idle.

## Communication
- Chairman to Agent: company/chairman_inbox/
- Agent to Chairman: company/chairman_outbox/
- Dashboard: tunnel URL (见 context_state.json) 或 http://localhost:8765 (本地)
- WeChat: outbox_watcher picks up ALERT/NOTIFY files

## Task Flow
1. Read TASK_TRACKER.md - find next pending task
2. Auto-execute or check if needs chairman approval
3. Execute using mature frameworks
4. Update TASK_TRACKER.md
5. If blocked/dangerous: write chairman_outbox/ and skip

## Project
- company/ - departments, frontend, server
- quant_framework/ - data, strategies, risk, backtest, execution
- TASK_TRACKER.md - master task list (171 done)
- KNOWLEDGE_GRAPH.md, RESEARCH_ROADMAP.md
"""

with open(os.path.join(base, 'SKILL.md'), 'w', encoding='utf-8') as f:
    f.write(main_md)
print('Main SKILL.md written')

# ── Department sub-skills ──
dept_skills = {
    'ceo_office': ('CEO Office - master coordination, inbox/outbox management, task dispatch', ['ceo', 'orchestration', 'inbox', 'dispatch']),
    'extreme_drive': ('Relentless execution, no task left behind, deadline enforcement', ['execution', 'drive', 'deadline']),
    'strategy_research': ('Factor discovery, alpha generation, IC analysis, strategy backtesting', ['strategy', 'factor', 'alpha', 'research']),
    'risk_management': ('VaR, CVaR, stress testing, portfolio optimization, drawdown control', ['risk', 'var', 'portfolio', 'optimization']),
    'data_engineering': ('Pipeline, ETL, market data fetch/clean/store/validate', ['data', 'pipeline', 'etl', 'market-data']),
    'it_tech': ('FastAPI server, dashboard, API endpoints, frontend, SSE push', ['fastapi', 'dashboard', 'api', 'frontend']),
    'backtest_engine': ('Vectorized/event-driven backtesting, strategy comparison, metrics', ['backtest', 'vectorized', 'comparison']),
    'trading_execution': ('Broker bridge (Alpaca), order simulation, position sizing, cost analysis', ['trading', 'execution', 'alpaca', 'broker']),
    'sentiment_intel': ('News analysis, social media NLP, market sentiment signals', ['sentiment', 'nlp', 'news', 'finbert']),
    'academic_research': ('Paper review, replication, methodology validation', ['academic', 'paper', 'replication', 'review']),
    'open_source_research': ('Quant project evaluation, GitHub scanning, framework comparison', ['open-source', 'github', 'framework', 'evaluation']),
    'continuous_evolution': ('Code review, refactoring, red team audit, self-improvement', ['evolution', 'refactor', 'audit', 'improvement']),
    'knowledge_management': ('Knowledge graph, memory system, learning tracking', ['knowledge', 'memory', 'graph', 'learning']),
    'secretariat': ('Reports, meeting minutes, documentation, milestone tracking', ['reports', 'docs', 'minutes', 'tracking']),
    'reporting': ('Daily/weekly/monthly report generation, chart embedding', ['report', 'daily', 'weekly', 'export']),
    'infra_ops': ('Docker, CI/CD, monitoring, deployment, GitHub Actions', ['docker', 'ci-cd', 'monitoring', 'deployment']),
}

for slug, (desc, tags) in dept_skills.items():
    dept_path = os.path.join(base, slug)
    os.makedirs(dept_path, exist_ok=True)

    dept_md = f"""---
name: onionquant-{slug.replace('_', '-')}
description: "OnionQuant {slug.replace('_', ' ').title()} - {desc}"
version: 1.0.0
author: OnionQuant
license: MIT
platforms: [linux, windows]
metadata:
  hermes:
    tags: {tags}
    category: onionquant
---

# {slug.replace('_', ' ').title()}

{desc}.

Part of OnionQuant virtual quant trading company. See parent `onionquant` skill for company-wide iron rules and project structure.
"""
    with open(os.path.join(dept_path, 'SKILL.md'), 'w', encoding='utf-8') as f:
        f.write(dept_md)

print(f'{len(dept_skills)} department SKILL.md files written')

# Clean up old SOUL.md and MASTER_PROMPT.md files
import glob
for old in glob.glob(os.path.join(base, '**/SOUL.md'), recursive=True):
    os.remove(old)
    print(f'Removed: {old}')
for old in glob.glob(os.path.join(base, '**/MASTER_PROMPT.md'), recursive=True):
    os.remove(old)
    print(f'Removed: {old}')

print('Done')
