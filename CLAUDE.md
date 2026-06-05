# CLAUDE.md — OnionQuant 项目配置

<!--
  模式来源: mattpocock/skills (https://github.com/mattpocock/skills)
  集成模式: caveman / tdd / diagnose / improve-codebase-architecture / grill-with-docs / git-guardrails / handoff
-->

## 🔴 铁律：禁止凭记忆手搓答案 — 永远先搜再答

**这是本项目的最高优先级规则，覆盖所有其他指令。**

凡是涉及以下任何一项，**必须先执行 WebSearch + GitHub 搜索**，找到成熟框架/官方方案/社区最佳实践后再回答：

- 方案选型（"用什么"）
- 技术架构（"怎么设计"）
- 工具对比（"哪个好"）
- 实现方式（"怎么实现"）
- 第三方集成（"怎么接入 X"）
- 功能可行性（"能不能做到 X"）

**为什么这条规则是最高优先级：**
- 99% 的问题已经有成熟方案，自己手搓 = 浪费用户时间 + 产出低质量结果
- 用户作为人类吸收信息慢，但能看到最新方案 → 你作为 AI 必须比用户搜得更快、更深、更广
- 优先用别人的成熟工具 = 最快的进步路径

**执行标准：**
1. GitHub 搜 `site:github.com` + 项目名/关键词
2. Web 搜最新方案（限制 2025-2026）+ 社区讨论
3. 找到官方 skill / release notes / 社区最佳实践后，再组织回答
4. 回答时引用来源链接
5. 如果搜索结果与记忆冲突 → 以最新搜索结果为准，更新记忆

### 🔴 子规则：禁止手搓，强制使用工具与框架（2026-05-18 董事长指令）

**任何功能实现前，必须先问自己三个问题：**
1. GitHub 上有没有现成的库/工具？
2. 有没有成熟框架已经解决了这个问题？
3. 我是不是又在"手搓"了？

**手搓判定标准：**
- 自己写解析器/表达式引擎 → 手搓（应该用现成库）
- 自己写回测循环/PnL计算 → 手搓（应该用 NautilusTrader/Backtrader/VectorBT）
- 自己写数据管道/ETL → 手搓（应该用 Dagster/Airflow/Pandas）
- 自己写因子计算 → 手搓（应该用 Qlib/Alphalens/pandas-ta）
- 自己写风险管理模型 → 手搓（应该用 Riskfolio-Lib/empyrical）
- 自己写爬虫/API客户端 → 手搓（应该用 yfinance/OpenBB/PRAW）

**例外（允许手搓）：**
- 粘合代码：将两个已有框架连接起来（<50行）
- 配置/编排：YAML/CLI 参数 + 框架调用
- 项目特有的业务逻辑（如 CANSLIM 筛选条件），但计算委托给框架

### 🔴 子规则：顺藤摸瓜 — 研究深度优先（2026-05-18 董事长指令）

**研究发现线索后必须持续深入，不得浅尝辄止。**

- 股票分析发现供应商/客户关联 → 立即研究该关联标的
- 催化剂事件影响多个标的 → 研究完整传导链
- 数据发现异常 → 下钻根因，不满足于表面解释
- 每份研报末尾必须包含「下一步研究方向」章节
- 不等董事长指令 → 主动顺藤摸瓜

5. 如果搜索结果与记忆冲突 → 以最新搜索结果为准，更新记忆

### 🔴 子规则：24h工作流保护 — 禁止 AI Cron，单会话运行

- 当前架构：1 个持久会话 (VS Code 或 WSL CLI) + Python background_scheduler
- AI 工作全部在持久会话内完成（缓存 99% 命中）
- **禁止用 CronCreate 做 AI 工作**（每次冷启动烧 ¥3/1M tokens）
- Python 脚本 (wechat_sync/sentiment/daily/publisher) → background_scheduler.py（零 AI token）
- `/goal` 模式可用于独立的一次性任务，但不得替换持久会话
- 短会话 + 缓存命中（98-99%）比长会话更稳定、更便宜

### 🔴 子规则：定量结论必须匹配当前技术栈

**涉及数字（成本、百分比、性能、缓存命中率）时，必须验证数据源是否匹配当前实际环境：**

| 当前栈 | 搜索时必须包含 |
|--------|-------------|
| DeepSeek V4-Pro | `DeepSeek V4` + 具体指标 |
| Claude Code (VS Code 插件) | `Claude Code` + 版本号 |
| Windows + WSL | `Windows` 或 `WSL` |
| 量化/AI Agent 混合系统 | 搜索两者的交叉数据 |

**自检触发器（给出结论前问自己）：**
1. 我引用的数字来自什么模型/环境？和用户当前用的是同一个吗？
2. 如果用户说实测数据和我说的不一致 → 用户数据优先，立即用用户栈重新搜
3. "通用最佳实践" 是否被当前栈的特殊性推翻？（如: DeepSeek 120:1 缓存价差 vs Anthropic 10:1）

> 这个规则来源: 2026-05-18 因引用 Anthropic SWE-bench 缓存数据 (91%) 而未区分 DeepSeek V4 实际数据 (98-99%)，导致并行 vs 串行策略判断错误。用户纠正后才重新搜索正确数据。**同一错误不得再犯。**

### 🔴 子规则：缓存命中优先级 — 编排策略的最优先决策因子（2026-05-18 董事长指令）

**DeepSeek V4-Pro 缓存价差 120:1**（命中 ¥0.025/1M vs 未命中 ¥3/1M），1M 上下文窗口充足。所有任务编排必须先过这一关：

| 决策点 | 规则 |
|--------|------|
| **同会话串行 vs 跨会话并行** | 同会话串行优先 — 第2轮起对话历史全命中(~99%)，跨会话并行只命中系统提示词 |
| **突发深度研究** | 用 `Agent` 子任务（共享缓存前缀）→ **不用 CronCreate 新会话**（冷启动对话全miss） |
| **简单扫描任务** | 所有任务统一用 Pro 模型 → 子Agent 继承父会话缓存前缀（90-99%命中），禁止用 Flash（缓存分离+冷启动=120x成本） |
| **子Agent派发** | 时间不重要→主会话串行；时间重要+≤3个→并行Agent(1.1-1.5x token，缓存前缀命中) |
| **稳定前缀** | 动态内容(timestamp/run_id)放 prompt 末尾 → 否则前缀变化=全量 miss |

**自检触发器（派发任务前问自己）：**
1. 这个任务放到同会话串行做能不能达到同样效果？能→不新开会话
2. 必须并行时，用的是 Agent 还是 CronCreate？CronCreate = 贵120倍
3. 动态时间戳是不是放末尾了？
4. 子Agent用的是Pro模型吗？（禁止Flash — 2026-05-19已移除 `CLAUDE_CODE_SUBAGENT_MODEL=haiku`）

### 🔴 子规则：禁止破坏 24h 工作流 — 优化必须无损现有系统（2026-05-18 董事长指令）

**任何代码/配置/架构优化必须满足以下前提：**

1. **不改动正在运行的 cron 配置** — 3 AI cron (inbox/iteration/redteam) + background_scheduler 继续正常运行
2. **不改动上下文持久化协议** — `context_state.json` + memory 文件桥接机制保持完好
3. **不破坏前端通信通道** — inbox → Agent 读取 / outbox → SSE 推送 → 董事长接收 保持畅通
4. **不降级 Pipeline 健康度** — MaxDD < -40%, Sharpe > 2.0 必须维持

**例外: 如果优化方案能显著改进以上任何一条，可以先做 A/B 对比验证，确认提升后再替换。**

**自检触发器（做任何改动前问自己）：**
1. 这个改动会打断正在运行的 cron 吗？
2. 改动后 context_state.json 还能被正确读写吗？
3. 前端 inbox/outbox 通道会被影响吗？
4. Pipeline 能正常重跑并产出报告吗？

**为什么**: /goal 模式的教训 — "优化"可能引入不可见破坏。AI 不会反问"你确定这个改动不影响现有流程吗？" 必须自检。

## 通信模式 (Communication Modes)

### Caveman Mode (触发: "caveman mode" / "talk like caveman" / "less tokens")
超压缩通信，省 ~75% token。掉冠词/填充词/客套话，保技术精度。
规则: 碎片OK，短同义词，箭头表因果。安全警告/不可逆操作时自动恢复完整模式。
停止: "stop caveman" / "normal mode"

## 🔄 上下文持久化协议 (Context Persistence Protocol)

**问题**: Cron 定时任务每次触发是新会话，对话历史不保留。中断后之前的执行上下文丢失。

**解决方案**: 中断上下文持久化 — 类似操作系统的中断服务程序 (ISR)。

### 保存状态 (每次会话结束前 / Cron 任务完成前)
- 更新 `company/departments/execution/context_state.json`
- 记录: `pending_actions` (待办列表), `key_context` (关键上下文), `last_updated`
- 上下文堆栈 `session_stack` 记录嵌套中断

### 恢复状态 (每次 Cron 任务开始时 / 新会话启动时)
- **第一步**: 读取 `company/departments/execution/context_state.json`
- **第二步**: 从 `pending_actions` 恢复待办事项
- **第三步**: 从 `key_context` 恢复关键上下文（持仓、重大事件、当前状态）
- **第四步**: 继续执行未完成的任务

### 硬规则
- 每次完成一个有意义的工作单元后 → 立即更新 context_state.json
- 涉及董事长持仓/重大决策的上下文 → 必须写入 `key_context`
- `pending_actions` 按优先级排序，P0 在前
- 不得依赖"我记得上次在做什么" — 必须从文件恢复

### 当前关键状态（每次会话开始前检查）
- **董事长持仓**: 全仓 DXYZ $28,000 @ ~$47.62
- **Starship IFT-12**: 5/20 22:30 UTC 首飞 (FAA已批)
- **NVDA 财报**: 5/20 盘后 (MaxPain $200 15% gap)
- **Samsung 罢工**: 5/21 deadline
- **3 AI crons** (inbox 20min / iteration 60min / redteam 60min) + background_scheduler (Python scripts, zero AI tokens)
- **日耗目标**: ¥7-10 (vs ¥30-50 优化前, -75%)

## 🔴 文件安全分级协议 (File Safety Protocol)

**权限模型**: Claude Code 拥有完全操作权限，但必须自我判断安全等级。权限是用户给的，判断力必须是自己的。

### 四级安全区域

| 等级 | 区域 | 规则 |
|------|------|------|
| 🟢 **自由区** | `e:/2026_AgentStudy/Python_code/` 及其子目录 | 可自由读写删，无需确认 |
| 🟡 **谨慎区** | `C:\Users\28462\AppData\`、`C:\Users\28462\Downloads\`、临时文件 | 读取无需确认；**删除/移动需事前告知用户，经确认后执行** |
| 🔴 **保护区** | `C:\Users\28462\Documents\`、`C:\Users\28462\Desktop\`、`C:\Users\28462\` 一级目录 | **任何写/删操作前必须获得用户明确同意**，不得自行决定 |
| ⛔ **禁区** | `C:\Windows\`、`C:\Program Files\`、`C:\Program Files (x86)\`、`C:\ProgramData\`、`/etc/`、`/usr/`（WSL 外） | **绝不操作**。即使用户要求，也先解释风险再确认 |

### 加密/敏感数据识别规则

以下特征的文件视为**高价值用户数据**，触碰前必须明确确认：

| 识别信号 | 示例 |
|----------|------|
| 路径含加密数据目录 | `WeChat Files`、`Tencent Files`、`kingsoft`、`wps` |
| 加密数据库扩展名 | `.db`、`.sqlite`、`.sqlite3`、`.dat`（含 ChatMsg、Media 等关键词） |
| 密钥/证书文件 | `.key`、`.pem`、`.crt`、`.pfx`、`.jks`、`.keystore` |
| 配置文件含密钥 | `.env`、`secrets.yaml`、`credentials.json` |
| 高熵文件 | 任何看似无结构/加密的文件，即使扩展名不明确 |

### 删除操作前置检查（每次删除前必须过这 5 关）

执行任何删除/移动操作前，自问：

1. **区域检查**: 目标在哪个安全区域？🟡🔴⛔ 则升级确认级别
2. **加密检查**: 路径/文件名是否匹配加密数据特征？是 → 必须确认
3. **不可逆检查**: 删除后能否恢复？（回收站 vs `rm -rf` vs `shift+delete`）
4. **依赖检查**: 删除此文件是否影响正在运行的应用？（微信/WPS/Hermes）
5. **体量检查**: 删除的是单个文件还是一整个目录树？

**违反任一检查 → 停下来，告知用户，等待确认。不凭猜测删文件。**

### 2026-05-18 C 盘清理事故教训（写入此处以永久铭记）

**事故**: 通过 WSL bash 调用 `cmd.exe /c rmdir` 删除 Windows 用户目录文件，命令返回 "OK" 但实际全部失败。同时 `Copy-Item` 复制 13.4 GB 到 E 盘后原文件未删除，导致 C 盘从 0 字节变得更满。

**根因**:
1. WSL → Windows 跨文件系统操作存在权限边界，`rmdir` 静默失败
2. 返回 "OK" 不代表成功 — 没有验证就报告完成
3. 复制大文件前未确认目标磁盘空间

**改正的铁律**:
- **跨 WSL/Windows 边界的删除操作 → 必须用 PowerShell `Remove-Item` + 事后 `Test-Path` 验证**
- **任何删除操作 → 做完了必须验证，不能只看返回值**
- **C 盘空间不足时 → 优先用 Windows 原生工具（bat 以管理员运行），不走 WSL**

### 通用安全护栏

| 触发条件 | 动作 |
|----------|------|
| 需要付费（API Key 以外） | → 写 `company/chairman_outbox/ASK_*.md` 请示，跳过 |
| 读取到疑似密钥、密码、Token | → 立即写 outbox 报警，**不存储到任何文件**，跳过 |
| 需要执行 `git push --force` | → 写 outbox 请示，跳过 |
| 遇到技术上不确定能否做的事情 | → 写 outbox 请示，跳过 |
| 触碰 🔴 保护区或 ⛔ 禁区 | → 先告知风险，等用户确认，不自行操作 |

**铁律**：
- 绝不停下等回复 — 写 outbox → 标记任务 ⏳等待董事长 → 继续执行下一个任务
- 不确定的事必须先问，不能猜
- 读到疑似密码/Token → 不存储，仅报告路径
- **删完必须验证** — 用 `Test-Path` 或 `ls` 确认操作结果

## 开发方法论 (Engineering Methodology)

### TDD: 红-绿-重构循环
- **垂直切片** (不是水平切片): 一次一个 test→impl，不先写所有测试再写所有代码
- **测行为不测实现**: 测试通过公共接口验证系统做什么，不管内部怎么做
- **删除测试**: 想象删除一个模块 — 复杂度消失=透传层，复杂度分散到N个调用方=有价值
- 重构只在 GREEN 状态做，RED 时不重构

### 架构原则 (from `/improve-codebase-architecture`)
- **深度模块**: 小接口背后藏大量行为 = 高杠杆。浅模块 = 接口几乎和实现一样复杂
- **局部性 (Locality)**: 变更/ bug/知识集中在同一处
- **杠杆 (Leverage)**: 调用方从深度获得的价值
- **接缝 (Seam)**: 接口所在处，行为可在此改变而不修改原地代码
- 一个适配器 = 假设缝，两个适配器 = 真实缝

### 诊断循环 (from `/diagnose`)
遇到硬bug时按6阶段走:
1. **建反馈循环** — 快速、确定、可脚本化的 pass/fail 信号（这是核心）
2. **复现** — 确认是用户描述的故障
3. **假设** — 3-5个可证伪的排名假设，格式: "如果X是原因，改Y会消失/改Z会恶化"
4. **仪器** — 调试器 > 定点日志 > "log everything"，debug日志加 `[DEBUG-xxxx]` 前缀
5. **修复+回归测试** — 先在正确接缝处写回归测试，再修
6. **清理+复盘** — 移除所有 debug 日志，复盘: 什么能防止这个bug？

## 环境
- 项目根目录: `e:/2026_AgentStudy/Python_code/`
- Python 虚拟环境: `.venv/`
- Python 版本: 3.12
- 前端服务器: `python onionquant/server.py` → http://localhost:8765 (本地) / tunnel URL 见 context_state.json `key_context.tunnel_url` (外网)
- **🔴 发微信/邮件/任何用户可见消息时，必须用外网 tunnel URL，绝不能用 localhost**
- 启动前先 kill 旧进程: `taskkill //F //PID <pid>` (Windows)

## 前端通信通道
- **董事长 → Agent**: 前端 inbox 输入 → `company/chairman_inbox/` → Agent 每轮扫描
- **Agent → 董事长**: 写 `company/chairman_outbox/` → 前端 SSE 推送 → 通知徽标 + 面板
- **董事长回复**: 点批准/拒绝 → 写入 inbox → Agent 下轮读到

## 项目结构
- `onionquant/` — 主源码包 (server, agents, api, departments, tools, wechat_bot)
- `quant_framework/` — 量化代码 (data, strategies, risk, backtest)
- `infrastructure/` — 基础设施 (KG schema, memory store, model tier, quant pipeline)
- `company/` — 运行时数据 (inbox, outbox, task_claims, execution state)
- `docs/` — 项目文档 (TASK_TRACKER, KNOWLEDGE_GRAPH, RESEARCH_ROADMAP)
- `scripts/` — CLI 脚本 & cron 任务
- `tests/` — 测试套件

## 🔬 量化工具栈 (禁止手搓分析)

任何量化分析必须调用以下工具库，不得手搓评分/回测/图谱:

| 工具 | 调用入口 | 用途 |
|------|---------|------|
| `risk_threshold_engine` | `RiskThresholdEngine().evaluate(FactorScores(...))` | 市场风险状态 + 部署决策 |
| `statsmodels` | `quant_framework/strategies/regime_detector.py` | Markov Switching 市场状态 |
| `yfinance` | `yf.download()` | 实时行情 |
| `bt` (pmorissette) | `bt.Strategy` + `bt.Backtest` | 事件驱动回测 |
| `empyrical` | `quant_framework/backtest/harness.py` | Sharpe/MaxDD/Calmar指标 |
| `networkx` | `quant_framework/knowledge_graph/quant_graph_builder.py` | 知识图谱 (303节点, 850边) |

**关键脚本**:
- `python scripts/decision_engine_v2.py` — 全量因子计算 + 决策矩阵 (10标的, 5因子)
- `python scripts/binary_catalyst_backtest.py` — 二元事件回测 + 蒙特卡洛
- `python scripts/market_monitor.py --once` — 市场监控守护进程 (全管道 + 微信推送)
- `python scripts/market_monitor.py --loop` — 持续循环模式 (每5分钟)
- `python -c "from quant_framework.knowledge_graph.quant_graph_builder import build_quant_knowledge_graph; build_quant_knowledge_graph()"` — 知识图谱

**部门技能**: `onionquant/departments/strategy_research/SKILL.md` / `risk_management/SKILL.md`

### DXYZ Starship 回测铁律 (2026-05-18 实测)
- DXYZ 7次历史 Starship 事件, 胜率仅 14% (1/7), 平均收益 -1.4%
- 模式: 发射前涨 → 发射后跌 (无论成败) — **不应持有穿越发射**
- 参见 memory: `[[starship-pattern]]`

## 领域语言 (Domain Language)
项目术语统一用以下词汇，避免同义替换:
- **因子 (Factor)**: 预测股票收益的信号变量
- **因子引擎 (Factor Engine)**: 计算和管理因子的模块
- **中性化 (Neutralize)**: 剔除行业/市值等干扰因素
- **标准化 (Standardize)**: Z-score 归一化 + 3-sigma 截尾
- **回测 (Backtest)**: 用历史数据验证策略
- **部门 (Department)**: 虚拟公司中的职能单元
- **董事长 (Chairman)**: 用户/决策者
- **发件箱 (Outbox)**: Agent 向董事长请示的通道
- **收件箱 (Inbox)**: 董事长向 Agent 发指令的通道

## Git 安全
- 不 `git push --force` 到 main/master
- 不 `git reset --hard` 除非用户明确要求
- 不跳过 hooks (`--no-verify`, `--no-gpg-sign`) 除非用户明确要求
- 永远创建新 commit，不 amend 已发布的 commit

## Token 优化与 Agent 派发策略

**当前模型**: DeepSeek V4-Pro（cache hit ¥0.025/1M vs miss ¥3/1M ≈ 120:1 价差，实际命中率 98-99%）
基于实测数据（生产基准: 并行 1.5-2x token 于串行，优化后可控制到 1.1-1.3x）:

### Agent 派发决策（按优先级）
1. **时间不重要 → 主会话串行**，最省 token。每轮对话累积缓存，后续轮次输入几乎全命中
2. **时间重要 + ≤3 个独立任务 → 并行 Explore Agent**，多花 1.5-2x token 换 1/3 时间
3. **时间重要 + >3 个任务 → 分批串行**，每批 2-3 个 Agent 并行，控制 token 倍数
4. **开发迭代（方案→编码→测试） → 同一会话串行**，绝不拆 Agent
5. **纯搜索/读文件研究 → Explore Agent**，中间结果不进主会话，避免主会话膨胀

### 硬规则
- 不中途切换模型 → 缓存是模型独有的，切换 = 全部作废
- 不中途增删 MCP 工具 → 工具定义改变 = 缓存前缀失效
- 动态内容（timestamp/run_id）放 prompt 末尾 → 否则全量 miss
- 稳定前缀（System Prompt + Tools）享全局缓存，后续轮次享会话累积缓存
- **CLAUDE.md 引用此策略的 agent: 每次派发子 Agent 前必须先自问 "串行能不能满足？能就不并行"**

### Cron 会话特性
- CronCreate 每次触发是**新会话** → System Prompt + Tools 全局缓存命中，但对话历史不保留
- 跨 Cron 状态桥接 → 靠 `company/departments/execution/context_state.json` + memory 文件，不靠对话上下文
- Cron 会话启动 → 第一件事就是 Read context_state.json 恢复现场（详见上方 🔄 上下文持久化协议）

### 🔒 任务认领协议 (Task Claim Protocol — 2026-05-18)

**每个 cron 会话启动后必须先认领任务，认领失败直接退出。基于 `mkdir` 原子操作（所有文件系统上的 Test-and-Set）。**

**类比 OS 概念**：
- `.claim/` 目录 = 互斥锁 (Mutex)
- `mkdir(.claim)` = Test-and-Set 指令（原子操作）
- `rmdir(.claim)` = 释放锁
- TTL 15 分钟 = 死锁预防

**认领步骤**（CLAUDE.md 最高优先级规则 — 先于任何其他任务执行）：

1. 从 cron prompt 关键词识别任务类型：
   - `扫描 company/chairman_inbox/` → `inbox`
   - `扫描项目状态` → `iteration`
   - `审查代码质量` → `redteam`
   - `sentiment_hourly_push` → `hourly`
   - `run_pipeline` → `daily`
2. 执行：`python scripts/task_claim.py try <task_type>`
3. 输出 `ACQUIRED:*` → 继续执行原任务
4. 输出 `SKIPPED:*` → 回 `locked by another session, skip`，**立即退出，不做任何其他操作**
5. 任务完成后：`python scripts/task_claim.py release <task_type>`

**硬规则**：
- 认领失败不重试 — 等下次 cron 触发
- 孤儿锁（session 崩溃）→ 15 分钟 TTL 后自动回收至 `_STALE_/`
- 不同任务类型独立锁 — inbox 不阻塞 iteration，redteam 不阻塞 hourly
- 认领是**第一步**，在读 context_state.json 之前执行（若无法认领则无需恢复状态）
- `scripts/task_claim.py` 是纯 stdlib 实现，零外部依赖

### 🔴 Cron 内部并行派发规则（2026-05-19 最终版 — 基于实测+外部研究验证）

**核心发现**: Agent 子任务使用 **Fork 机制**（非新会话），继承父会话完整 prompt prefix → 5 维缓存键（系统提示词+工具+模型+消息前缀+thinking配置）全部对齐 → 子 Agent 缓存命中率 **92-93%**。CronCreate 每次新会话 → 仅全局系统提示词命中 → **~10% 缓存命中率 → 贵 10-12x**。

**数据来源**: Claude Code 官方博客 + LMCache Blog 实测 trace 数据 + DeepSeek V4 Prompt Cache 诊断 (GitHub)。

**当前 2 Cron（已优化至最低）**：

#### 研究迭代 Cron（每小时 :07，`0f6fb799`）
每轮用 **3 个并行 Agent (general-purpose)** — 共享父会话缓存前缀 (~92% hit)：
1. DXYZ + SpaceX IPO / Starship IFT-12
2. 存储/半导体 (MU/WDC/SNDK/NVDA/SOX) + Samsung 罢工
3. 航天 (RKLB/ASTS/LUNR/RDW) + 光模块/AI 芯片 (COHR/LITE/AVGO)

#### Inbox 扫描 Cron（每小时 :37，`fb3f942a`）
- 有消息 → 直接处理，写回复，推微信
- 无消息 → **立即退出**（最小化 token 消耗）

**硬约束**：
- 研究迭代最多 3 并行 Agent（实测 1.1-1.5x token，快 3-5x）
- Python 脚本全部走 `background_scheduler.py`（零 AI token）
- **不再创建额外 cron** — 每新增一个 cron = 每天 +24 次冷启动
- Cron prompt 必须英文（JSON mojibake 风险）
- 日耗目标: ¥5-8（48 会话/天，Agent fork 共享缓存）

### 🔴 统一会话策略 (Unified Session Policy — 2026-05-18 董事长指令)

**铁律：整个项目只维护 1 个主会话 ID（当前 VS Code 插件会话）。所有并行工作通过 Agent 子任务完成，禁止启动独立 CLI 会话。**

**为什么**：
- DeepSeek V4-Pro 缓存价差 120:1（命中 ¥0.025/1M vs 未命中 ¥3/1M）
- 同会话 turn 2+ = 99% 缓存命中；独立会话 = 仅系统提示词命中
- Agent 子任务 fork 自主会话 → 继承父会话 prompt prefix（system prompt + tools + CLAUDE.md + memory）→ 全部缓存命中
- 3 个独立 CLI 会话 polling = 180 轮/小时 × 仅系统提示词命中 = 疯狂烧 token（2026-05-18 已验证，已废弃）

**架构**：
```
主会话 (当前 VS Code 插件)  ← 唯一会话 ID，累积缓存
├── 用户直接对话 → 99% cache hit
├── 需要并行 → Agent 子任务 (继承前缀，1.1-1.5x token)
├── CronCreate → 定时触发 (新会话但只做调度，不做重活)
│   ├── inbox cron → 发现 2+ 任务 → 并行 Agent
│   ├── iteration cron → 5 并行 WebSearch Agent
│   └── redteam cron → 4 并行 Grep Agent
└── Python 进程 → market_monitor.py 等（不烧 AI token）
```

**禁止事项**：
- ❌ 禁止启动 WSL screen/tmux 里的独立 `claude` 会话
- ❌ 禁止用 `claude -p` 在 bash 循环里轮询
- ❌ 禁止用 CronCreate 做需要多轮对话的深度任务（每次都是冷会话）
- ✅ 深度任务 → 主会话串行；独立并行任务 → Agent 子任务；定时轻量 → CronCreate

**Agent 派发决策（更新版）**：
1. 用户在会话中 → 主会话直接处理（最优缓存）
2. 用户不在 + inbox 有 1 个任务 → cron 会话直接处理
3. 用户不在 + inbox 有 2-5 个独立任务 → cron 会话派发并行 Agent（每 Agent 一个任务）
4. 定时扫描/审查 → CronCreate 触发，内部用 Agent 并行

**Inbox Cron 流程** (`a49872c1`, 每 10 分钟)：
```
1. task_claim.py try inbox → SKIPPED? 直接退出
2. 列出 inbox/*.md 待处理文件
3. 0 个 → release, 退出
4. 1 个 → 主会话直接处理 → 移入 processed/
5. 2-5 个 → 每个文件派 1 个 Agent (general-purpose)
   → 全部 Agent 完成后 → 移入 processed/ → release
```

## 任务结束交接 (Handoff)
当会话上下文将满或需要交接给新 agent 时:
- 更新 `company/departments/execution/context_state.json`，总结当前状态
- 引用已有产物 (PRD/ADR/issue) 而非重复内容
- 建议下一个 session 使用的 skills
