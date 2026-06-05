---
name: strategy-research
description: 策略研究部 — 因子计算·实时评分·交易决策矩阵 (yfinance + risk_threshold_engine + statsmodels + empyrical)
---

# 策略研究部 (Strategy Research Department)

## 工具栈 (非手搓)

| 工具 | 用途 | 调用方式 |
|------|------|---------|
| `risk_threshold_engine` | 市场风险状态 + 部署决策 | `RiskThresholdEngine().evaluate(FactorScores(...))` |
| `statsmodels` | Markov Switching 市场状态检测 | `quant_framework/strategies/regime_detector.py` |
| `yfinance` | 实时行情数据 | `yf.download(tickers, period="6mo")` |
| `empyrical` | Sharpe/MaxDD/Calmar 等标准指标 | `quant_framework/backtest/harness.py` |
| `bt` (pmorissette) | 事件驱动策略回测 | `bt.Strategy` + `bt.Backtest` |

## 触发条件

- 董事长指令: "分析XX标的" / "更新评分" / "今晚怎么操作"
- Cron 触发: 每小时自动更新因子评分
- 前端请求: Dashboard 点击"运行分析"

## 执行流程

1. `python scripts/decision_engine_v2.py` — 全量因子计算 + 决策矩阵
2. 结果写入 `company/chairman_outbox/DECISION_v2_*.json`
3. 仪表盘自动拉取最新决策数据

## 因子定义

| 因子 | 权重 | 数据源 | 计算库 |
|------|------|--------|--------|
| 动量 (5d/20d) | 20% | yfinance Close | pandas pct_change |
| 波动率 | 15% | yfinance daily returns | numpy std * sqrt(252) |
| Sharpe 比率 | 25% | excess returns vs 2% RF | empyrical via harness |
| 催化事件 | 30% | CATALYST_CALENDAR (手动维护) | 事件计数 × magnitude |
| Beta 惩罚 | 10% | WATCHLIST beta_spx | ≥1.5 扣分 |

## 铁律

- 不用大模型猜数字 — 所有因子由库计算
- 因子权重可调，但调整后必须回测验证
- 评分结果写入 outbox 供董事长审核
