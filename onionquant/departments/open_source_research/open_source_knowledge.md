# 开源量化项目知识图谱

> 生成日期：2026-05-17
> 目的：构建开源量化金融项目之间的关联关系，辅助技术选型决策

---

## 一、项目生态全景图

```
                         ┌──────────────────────────────────┐
                         │      数据层 (Data Layer)          │
                         │  yfinance · OpenBB · gs-quant    │
                         │  Alphalens · Pyfolio              │
                         └──────────────┬───────────────────┘
                                        │
                         ┌──────────────┴───────────────────┐
                         │      研究层 (Research Layer)      │
                         │  Qlib · Kronos · FinGPT          │
                         │  FinRL/FinRL-X · TensorTrade      │
                         └──────────────┬───────────────────┘
                                        │
                         ┌──────────────┴───────────────────┐
                         │      回测层 (Backtest Layer)      │
                         │  VectorBT · LEAN · backtrader    │
                         │  Zipline-Reloaded · NautilusTrdr │
                         └──────────────┬───────────────────┘
                                        │
                         ┌──────────────┴───────────────────┐
                         │      优化层 (Optimization Layer)  │
                         │  PyPortfolioOpt · Riskfolio-Lib  │
                         └──────────────┬───────────────────┘
                                        │
                         ┌──────────────┴───────────────────┐
                         │      执行层 (Execution Layer)     │
                         │  LEAN · vnpy · NautilusTrader    │
                         │  TradingAgents · AI Hedge Fund   │
                         └──────────────────────────────────┘
```

---

## 二、项目间关联关系

### 2.1 依赖与互补关系

```
yfinance ──提供数据──▶ Qlib
yfinance ──提供数据──▶ FinRL
yfinance ──提供数据──▶ VectorBT
yfinance ──提供数据──▶ backtrader
yfinance ──提供数据──▶ Zipline-Reloaded
     │
OpenBB ──提供数据──▶ 任何项目 (MCP协议)
OpenBB ──内置AI──▶ AI Copilot (LLaMA)
     │
Alphalens ──因子分析──▶ Pyfolio ──组合分析──▶ 策略优化
     │
PyPortfolioOpt ──可用于──▶ Qlib (组合优化模块)
Riskfolio-Lib ──可用于──▶ Qlib (风险度量补充)
     │
FinRL ──DRL训练──▶ LEAN/NautilusTrader (执行交易)
FinRL-X ──ML+DRL+LLM──▶ 可直接部署实盘
     │
Kronos ──K线预测──▶ Qlib/VectorBT (集成预测信号)
     │
FinGPT ──情感分析──▶ Qlib/FinRL (情感因子输入)
     │
TradingAgents ──多智能体──▶ 任何回测引擎 (信号输出)
AI Hedge Fund ──大师智能体──▶ 任何回测引擎 (聚合信号)
```

### 2.2 竞争/替代关系

```
回测引擎竞争轴:
  VectorBT (向量化-高性能)
      vs
  backtrader (事件驱动-已停维)
      vs
  LEAN (事件驱动-工业级)
      vs
  NautilusTrader (Rust-极速)

AI平台竞争轴:
  Qlib + RD-Agent (微软-全流程AI)
      vs
  FinRL-X (AI4Finance-RL+ML+LLM)
      vs
  TradingAgents (多智能体LLM)

数据平台竞争轴:
  OpenBB (66K Stars, 综合平台)
      vs
  yfinance (专注Yahoo数据, 简单高效)
```

---

## 三、"全球最强美股量化系统"架构映射

### 推荐架构：分层解耦 + 模块化组合

```
┌─────────────────────────────────────────────────────────────────┐
│                     美股量化系统架构 v1.0                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                       数据层                              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐     │  │
│  │  │  yfinance   │  │   OpenBB    │  │  gs-quant    │     │  │
│  │  │  (实时行情)  │  │  (多源整合)  │  │  (衍生品数据) │     │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘     │  │
│  └───────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│  ┌───────────────────────┴───────────────────────────────────┐  │
│  │                    特征/研究层                             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐     │  │
│  │  │   Qlib      │  │   FinGPT    │  │   Kronos     │     │  │
│  │  │  (AI因子)   │  │  (情感分析)  │  │  (K线预测)    │     │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘     │  │
│  │  ┌─────────────┐  ┌─────────────┐                       │  │
│  │  │   FinRL-X   │  │ Alphalens   │                       │  │
│  │  │  (RL训练)   │  │ (因子分析)   │                       │  │
│  │  └─────────────┘  └─────────────┘                       │  │
│  └───────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│  ┌───────────────────────┴───────────────────────────────────┐  │
│  │                     回测/优化层                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐     │  │
│  │  │  VectorBT   │  │   LEAN /    │  │PyPortfolioOpt│     │  │
│  │  │  (参数扫描)  │  │NautilusTrdr │  │/Riskfolio    │     │  │
│  │  │             │  │  (事件回测)  │  │ (组合优化)    │     │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘     │  │
│  └───────────────────────┬───────────────────────────────────┘  │
│                          │                                      │
│  ┌───────────────────────┴───────────────────────────────────┐  │
│  │                      执行层                                │  │
│  │  ┌─────────────┐  ┌─────────────┐                        │  │
│  │  │   LEAN /    │  │ TradingAgents│                        │  │
│  │  │NautilusTrdr │  │(AI辅助决策)  │                        │  │
│  │  │  (实盘交易)  │  │             │                        │  │
│  │  └─────────────┘  └─────────────┘                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                      监控/风控层                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐     │  │
│  │  │   Pyfolio   │  │  gs-quant   │  │   OpenBB     │     │  │
│  │  │  (绩效报告)  │  │  (衍生品风控)│  │  (实时仪表盘) │     │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、项目质量评估矩阵

### 4.1 活性评估（Maintenance Health）

```
项目名称         Stars    最后更新    更新频率    健康度
──────────     ─────    ────────    ────────    ────
OpenBB          66.6K   2026-04     持续高频     ●●●●●
Qlib            42.0K   2026-04     持续        ●●●●●
NautilusTrader  22.5K   2026-05     双周发布     ●●●●○
yfinance        23.2K   2026-04     持续        ●●●●●
FinGPT          19.9K   2026-04     v1.0发布    ●●●●○
Freqtrade       50.0K   2026-04    月度发布     ●●●●●
FinRL-X         15.1K   2026-03    活跃        ●●●●○
LEAN            19.0K   2026-04    持续        ●●●●○
VectorBT         7.5K   2026-04    v1.0发布    ●●●●○
gs-quant        10.2K   2026-04    持续        ●●●●○
Kronos          25.0K   2026-05    AAAI 2026   ●●●●○
TradingAgents   71.4K   2026-05    高速成长     ●●●●○
AI Hedge Fund   55.0K   2026-04    新兴        ●●●○○
PyPortfolioOpt   4.6K   近年       低频        ●●●○○
Riskfolio-Lib    3.1K   近年       低频        ●●●○○
vnpy            40.3K   2026-01    低频        ●●●○○
zipline-reloaded 1.7K   近年       不活跃      ●●○○○
backtrader      21.2K   2019       已停维      ●○○○○
Alphalens        4.1K   2020       已停维      ●○○○○
Pyfolio          4.9K   近年       已停维      ●●○○○
TensorTrade      6.1K   近年       停滞        ●●○○○
```

### 4.2 技术栈分布

```
Python库:       yfinance, Qlib, FinGPT, FinRL, VectorBT, backtrader, 
               Alphalens, Pyfolio, PyPortfolioOpt, Riskfolio-Lib,
               Freqtrade, TensorTrade, TradingAgents, AI Hedge Fund

Python+C#:     LEAN (QuantConnect)

Python+Rust:   NautilusTrader

Jupyter NB:    FinGPT, Kronos, FinRL

Python+React:  AI Hedge Fund
```

### 4.3 许可证兼容性

```
MIT (最宽松):    Qlib, vnpy, VectorBT, FinRL, FinGPT, Kronos, 
               OpenBB, PyPortfolioOpt, Riskfolio-Lib, AI Hedge Fund

Apache-2.0:    LEAN, yfinance, Alphalens, Pyfolio, gs-quant,
               Zipline, TensorTrade, TradingAgents

GPL-3.0:       backtrader, Freqtrade

LGPL-3.0:      NautilusTrader
```

---

## 五、关键发现与战略结论

### 5.1 六大趋势（2026年）

| # | 趋势 | 代表项目 | 战略影响 |
|---|------|---------|---------|
| 1 | **AI多智能体交易** | TradingAgents, AI Hedge Fund | LLM智能体替代传统量化策略 |
| 2 | **金融基础模型** | Kronos (AAAI 2026) | K线+Transformer，预测能力质变 |
| 3 | **全栈AI量化平台** | Qlib + RD-Agent | 微软持续重注AI量化 |
| 4 | **高性能Rust引擎** | NautilusTrader | Rust成为量化基础设施新选择 |
| 5 | **开源Bloomberg替代** | OpenBB (66K Stars) | 数据民主化，AI Agent数据入口 |
| 6 | **RL+LLM融合** | FinRL-X | 强化学习与大语言模型协同 |

### 5.2 关键战略建议

**1. 立即采用（P0）：**
- OpenBB Terminal 作为数据中台（美股数据全覆盖 + MCP协议）
- Qlib 作为AI研究核心（RD-Agent自动因子挖掘）
- yfinance 作为轻量级数据补充
- VectorBT 作为高性能回测/参数优化工具

**2. 快速集成（P1）：**
- Kronos 增强K线预测能力
- FinRL-X 增强RL交易能力
- FinGPT 增强情感分析和文本分析
- LEAN/NautilusTrader 生产级回测和实盘交易

**3. 战略观察（P2）：**
- TradingAgents 是多智能体LLM交易的代表，潜力巨大但需验证
- AI Hedge Fund 概念创新，适合作为灵感来源
- Riskfolio-Lib 可在尾部风险管理场景下使用

**4. 不推荐使用（Deprecated）：**
- backtrader（已停维）
- Zipline原始版本（已停维）
- TensorTrade（Beta停滞）

### 5.3 差异化竞争优势

基于本次调研，构建"全球最强美股量化系统"的差异化竞争策略：

```
核心差异化 = OpenBB(数据) + Qlib(AI研究) + Kronos(K线预测) + FinRL-X(RL执行)
            + TradingAgents(LLM智能体)
            ─────────────────────────────────────
            形成 "数据 + AI因子 + K线预测 + RL执行 + LLM智能体" 五层闭环
```

此架构在以下维度具备竞争力：
- **数据层**：OpenBB的100+数据源超过任何单一项目
- **AI因子**：Qlib的RD-Agent自动挖掘能力行业领先
- **K线预测**：Kronos的120亿K线预训练基础模型
- **RL执行**：FinRL-X的DRL+ML+LLM混合架构
- **LLM智能体**：TradingAgents的多智能体协作方式代表前沿

---

## 六、附录：快速查询表

### 按功能分类

| 需求 | 首选 | 备选 |
|------|------|------|
| 美股数据获取 | yfinance | OpenBB |
| 多源数据整合 | OpenBB | - |
| AI因子挖掘 | Qlib (RD-Agent) | - |
| K线预测 | Kronos | Qlib内置模型 |
| 情感分析 | FinGPT | FinBERT |
| 强化学习交易 | FinRL-X | FinRL |
| 向量化回测 | VectorBT | - |
| 事件驱动回测 | LEAN | NautilusTrader |
| 组合优化 | PyPortfolioOpt | Riskfolio-Lib |
| 衍生品分析 | gs-quant | - |
| 因子分析 | Alphalens | Qlib内置 |
| 绩效报告 | Pyfolio | QuantStats |
| 实盘交易 | LEAN (QuantConnect) | NautilusTrader |
| LLM多智能体 | TradingAgents | AI Hedge Fund |
| 加密货币 | Freqtrade | - |

### 按Stars排名

| 排名 | 项目 | Stars |
|------|------|-------|
| 1 | TradingAgents | 71,400 |
| 2 | OpenBB | 66,600 |
| 3 | AI Hedge Fund | 55,000 |
| 4 | Freqtrade | 50,000 |
| 5 | Qlib | 42,000 |
| 6 | vnpy | 40,300 |
| 7 | daily_stock_analysis | 32,000 |
| 8 | Kronos | 25,000 |
| 9 | yfinance | 23,200 |
| 10 | NautilusTrader | 22,450 |

---

*知识图谱版本 1.0 | 最后更新：2026-05-17*
